#!/usr/bin/env python3
# Copyright 2022 Guillaume Belanger
# See LICENSE file for licensing details.

"""Charmed operator for the 5G AMF service."""

import logging

from ops.charm import CharmBase, InstallEvent, PebbleReadyEvent, RemoveEvent
from ops.main import main
from ops.model import ActiveStatus, WaitingStatus
from ops.pebble import ExecError, Layer

from kubernetes import Kubernetes

logger = logging.getLogger(__name__)


class QuaggaOperatorCharm(CharmBase):
    """Main class to describe juju event handling for the 5G AMF operator."""

    def __init__(self, *args):
        super().__init__(*args)
        self._container_name = self._service_name = "quagga"
        self._container = self.unit.get_container(self._container_name)
        self._kubernetes = Kubernetes(namespace=self.model.name)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.remove, self._on_remove)
        self.framework.observe(self.on.quagga_pebble_ready, self._on_quagga_pebble_ready)

    def _on_install(self, event: InstallEvent) -> None:
        """Handle the install event."""
        self._kubernetes.create_network_attachment_definition()
        self._kubernetes.patch_statefulset(statefulset_name=self.app.name)

    def _on_quagga_pebble_ready(self, event: PebbleReadyEvent) -> None:
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for workload container to be ready")
            event.defer()
            return
        self._prepare_container()
        self._container.add_layer("quagga", self._pebble_layer, combine=True)
        self._container.replan()
        self.unit.status = ActiveStatus()

    def _prepare_container(self):
        self._set_ip_forwarding()
        self._set_ip_tables()
        self._set_ip_route()
        self._trap_signals()

    def _set_ip_forwarding(self):
        if not self._container.can_connect():
            raise RuntimeError("Container is not ready")
        process = self._container.exec(
            command=["/bin/bash", "-c", "sysctl -w net.ipv4.ip_forward=1"],
        )
        try:
            process.wait_output()
        except ExecError as e:
            logger.error("Exited with code %d. Stderr:", e.exit_code)
            for line in e.stderr.splitlines():  # type: ignore[union-attr]
                logger.error("    %s", line)
            raise e
        logger.info("Successfully set ip forwarding")

    def _set_ip_tables(self):
        if not self._container.can_connect():
            raise RuntimeError("Container is not ready")
        process = self._container.exec(
            command=["/bin/bash", "-c", "iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE"],
        )
        try:
            process.wait_output()
        except ExecError as e:
            logger.error("Exited with code %d. Stderr:", e.exit_code)
            for line in e.stderr.splitlines():  # type: ignore[union-attr]
                logger.error("    %s", line)
            raise e
        logger.info("Successfully set ip tables")

    def _set_ip_route(self):
        if not self._container.can_connect():
            raise RuntimeError("Container is not ready")
        process = self._container.exec(
            command=["/bin/bash", "-c", "ip route add 172.250.0.0/16 via 192.168.250.3"],
        )
        try:
            process.wait_output()
        except ExecError as e:
            logger.error("Exited with code %d. Stderr:", e.exit_code)
            for line in e.stderr.splitlines():  # type: ignore[union-attr]
                logger.error("    %s", line)
            raise e
        logger.info("Successfully set ip routes")

    def _trap_signals(self):
        if not self._container.can_connect():
            raise RuntimeError("Container is not ready")
        process = self._container.exec(
            command=["/bin/bash", "-c", "trap : TERM INT"],
        )
        try:
            process.wait_output()
        except ExecError as e:
            logger.error("Exited with code %d. Stderr:", e.exit_code)
            for line in e.stderr.splitlines():  # type: ignore[union-attr]
                logger.error("    %s", line)
            raise e
        logger.info("Successfully set trap signals")

    def _on_remove(self, event: RemoveEvent) -> None:
        self._kubernetes.delete_network_attachment_definition()

    @property
    def _pebble_layer(self) -> Layer:
        """Returns pebble layer for the charm.

        Returns:
            Layer: Pebble Layer
        """
        return Layer(
            {
                "summary": "quagga layer",
                "description": "pebble config layer for quagga",
                "services": {
                    "quagga": {
                        "override": "replace",
                        "startup": "enabled",
                        "command": "sleep infinity",
                    },
                },
            }
        )


if __name__ == "__main__":
    main(QuaggaOperatorCharm)
