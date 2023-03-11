#!/usr/bin/env python3
# Copyright 2022 Guillaume Belanger
# See LICENSE file for licensing details.

"""Charmed operator for the 5G AMF service."""

import json
import logging
from typing import List

from ops.charm import CharmBase, InstallEvent, PebbleReadyEvent, RelationChangedEvent, RemoveEvent
from ops.main import main
from ops.model import ActiveStatus
from ops.pebble import ExecError, Layer

from kubernetes import Kubernetes

logger = logging.getLogger(__name__)


class QuaggaRouterOperatorCharm(CharmBase):
    """Main class to describe juju event handling for the 5G AMF operator."""

    def __init__(self, *args):
        super().__init__(*args)
        self._container_name = self._service_name = "router"
        self._container = self.unit.get_container(self._container_name)
        self._kubernetes = Kubernetes(namespace=self.model.name, statefulset_name=self.app.name)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.remove, self._on_remove)
        self.framework.observe(self.on.router_pebble_ready, self._on_router_pebble_ready)
        self.framework.observe(self.on.router_relation_changed, self._on_router_relation_changed)

    def _on_install(self, _: InstallEvent) -> None:
        """Handle the install event."""
        self._kubernetes.create_network_attachment_definition()
        self._kubernetes.add_security_context_to_statefulset()

    def _on_router_pebble_ready(self, _: PebbleReadyEvent) -> None:
        self._prepare_container()
        self._container.add_layer("router", self._pebble_layer, combine=True)
        self._container.replan()
        self.unit.status = ActiveStatus()

    def _on_router_relation_changed(self, event: RelationChangedEvent) -> None:
        if not self._container.can_connect():
            event.defer()
            return
        if not event.unit:
            return
        remote_unit_relation_data = event.relation.data[event.unit]
        interface_name = remote_unit_relation_data.get("name", None)
        gateway = remote_unit_relation_data.get("gateway", None)
        routes = remote_unit_relation_data.get("routes", None)
        if not interface_name or not gateway:
            logger.info("Missing info from relation data")
            return
        self._kubernetes.add_multus_annotation_to_statefulset(
            interface_name=interface_name, ips=[gateway]
        )
        if routes:
            routes_list = json.loads(routes)
            for route in routes_list:
                self._set_ip_route(network=route["network"], gateway_ip=route["gateway"])

    def _prepare_container(self) -> None:
        self._set_ip_forwarding()
        self._set_ip_tables()
        self._trap_signals()

    def _set_ip_forwarding(self) -> None:
        self._run_command_in_workload(
            command=["/bin/bash", "-c", "sysctl -w net.ipv4.ip_forward=1"]
        )
        logger.info("Successfully set ip forwarding")

    def _set_ip_tables(self):
        self._run_command_in_workload(
            command=["/bin/bash", "-c", "iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE"]
        )
        logger.info("Successfully set ip tables")

    def _set_ip_route(self, network: str, gateway_ip: str) -> None:
        self._run_command_in_workload(
            command=["/bin/bash", "-c", f"ip route add {network} via {gateway_ip}"]
        )
        logger.info(f"Successfully set ip route: {network} via {gateway_ip}")

    def _trap_signals(self):
        self._run_command_in_workload(command=["/bin/bash", "-c", "trap : TERM INT"])
        logger.info("Successfully set trap signals")

    def _run_command_in_workload(self, command: List[str]):
        if not self._container.can_connect():
            raise RuntimeError("Container is not ready")
        process = self._container.exec(command=command)
        try:
            process.wait_output()
        except ExecError as e:
            logger.error("Exited with code %d. Stderr:", e.exit_code)
            for line in e.stderr.splitlines():  # type: ignore[union-attr]
                logger.error("    %s", line)
            raise e

    def _on_remove(self, _: RemoveEvent) -> None:
        self._kubernetes.delete_network_attachment_definition()

    @property
    def _pebble_layer(self) -> Layer:
        """Returns pebble layer for the charm.

        Returns:
            Layer: Pebble Layer
        """
        return Layer(
            {
                "summary": "router layer",
                "description": "pebble config layer for router",
                "services": {
                    "router": {
                        "override": "replace",
                        "startup": "enabled",
                        "command": "sleep infinity",
                    },
                },
            }
        )


if __name__ == "__main__":
    main(QuaggaRouterOperatorCharm)
