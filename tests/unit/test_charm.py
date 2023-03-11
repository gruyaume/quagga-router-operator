# Copyright 2022 Guillaume Belanger
# See LICENSE file for licensing details.

import json
import unittest
from unittest.mock import Mock, patch

from ops import testing
from ops.model import ActiveStatus

from charm import QuaggaRouterOperatorCharm


class TestCharm(unittest.TestCase):
    @patch("lightkube.core.client.GenericSyncClient")
    def setUp(self, patch_k8s_client):
        self.namespace = "whatever"
        self.harness = testing.Harness(QuaggaRouterOperatorCharm)
        self.harness.set_model_name(name=self.namespace)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @patch("kubernetes.Kubernetes.add_security_context_to_statefulset")
    @patch("kubernetes.Kubernetes.create_network_attachment_definition")
    def test_given_when_on_install_then_security_context_is_added_to_statefulset(
        self, patch_security_context, patch_create_network_attachment_definition
    ):
        self.harness.charm.on.install.emit()

        patch_create_network_attachment_definition.assert_called()
        patch_security_context.assert_called()

    @patch("kubernetes.Kubernetes.delete_network_attachment_definition")
    def test_given_when_on_remove_then_network_attachment_definition_is_deleted(
        self, patch_delete_network_attachment_definition
    ):
        self.harness.charm.on.remove.emit()

        patch_delete_network_attachment_definition.assert_called()

    @patch("ops.model.Container.exec", new=Mock())
    def test_given_can_connect_when_pebble_ready_then_pebble_plan_is_applied(
        self,
    ):
        self.harness.container_pebble_ready(container_name="router")

        expected_plan = {
            "services": {
                "router": {
                    "startup": "enabled",
                    "override": "replace",
                    "command": "sleep infinity",
                }
            }
        }

        updated_plan = self.harness.get_container_pebble_plan("router").to_dict()

        self.assertEqual(expected_plan, updated_plan)

    @patch("ops.model.Container.exec", new=Mock())
    def test_given_can_connect_to_container_when_pebble_ready_then_status_is_active(self):
        self.harness.container_pebble_ready(container_name="router")

        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    @patch("kubernetes.Kubernetes.add_multus_annotation_to_statefulset")
    def test_given_name_and_gateway_in_relation_data_when_relation_changed_then_multus_annotation_added_to_statefulset(  # noqa: E501
        self, patch_add_multus_annotation
    ):
        self.harness.set_can_connect(container="router", val=True)
        interface_name = "whatever name"
        gateway_address = "1.2.3.4/24"
        relation_data = {
            "name": interface_name,
            "gateway": gateway_address,
        }
        relation_id = self.harness.add_relation(
            relation_name="router", remote_app="router-requirer"
        )
        self.harness.add_relation_unit(
            relation_id=relation_id, remote_unit_name="router-requirer/0"
        )
        self.harness.update_relation_data(
            relation_id=relation_id, app_or_unit="router-requirer/0", key_values=relation_data
        )

        patch_add_multus_annotation.assert_called_with(
            interface_name=interface_name, ips=[gateway_address]
        )

    @patch("kubernetes.Kubernetes.add_multus_annotation_to_statefulset")
    def test_given_routes_in_relation_data_but_no_gateway_when_relation_changed_then_multus_annotation_not_added_to_statefulset(  # noqa: E501
        self, patch_add_multus_annotation
    ):
        self.harness.set_can_connect(container="router", val=True)
        routes = [
            {"network": "172.250.0.0/16", "gateway": "192.168.250.3"},
            {"network": "172.250.0.0/16", "gateway": "192.168.250.5"},
        ]
        relation_data = {"routes": json.dumps(routes)}

        relation_id = self.harness.add_relation(
            relation_name="router", remote_app="router-requirer"
        )
        self.harness.add_relation_unit(
            relation_id=relation_id, remote_unit_name="router-requirer/0"
        )
        self.harness.update_relation_data(
            relation_id=relation_id, app_or_unit="router-requirer/0", key_values=relation_data
        )

        patch_add_multus_annotation.assert_not_called()

    @patch("ops.model.Container.exec", new=Mock())
    @patch("kubernetes.Kubernetes.add_multus_annotation_to_statefulset")
    def test_given_routes_and_gateway_in_relation_data_when_relation_changed_then_multus_annotation_added_to_statefulset(  # noqa: E501
        self, patch_add_multus_annotation
    ):
        self.harness.set_can_connect(container="router", val=True)
        interface_name = "whatever name"
        gateway_address = "1.2.3.4/24"
        routes = [
            {"network": "172.250.0.0/16", "gateway": "192.168.250.3"},
            {"network": "172.250.0.0/16", "gateway": "192.168.250.5"},
        ]
        relation_data = {
            "name": interface_name,
            "gateway": gateway_address,
            "routes": json.dumps(routes),
        }

        relation_id = self.harness.add_relation(
            relation_name="router", remote_app="router-requirer"
        )
        self.harness.add_relation_unit(
            relation_id=relation_id, remote_unit_name="router-requirer/0"
        )
        self.harness.update_relation_data(
            relation_id=relation_id, app_or_unit="router-requirer/0", key_values=relation_data
        )

        patch_add_multus_annotation.assert_called_with(
            interface_name=interface_name, ips=[gateway_address]
        )

    @patch("ops.model.Container.exec")
    @patch("kubernetes.Kubernetes.add_multus_annotation_to_statefulset")
    def test_given_routes_in_relation_data_when_relation_changed_then_route_is_added_to_workload(
        self, _, patch_exec
    ):
        self.harness.set_can_connect(container="router", val=True)
        interface_name = "whatever name"
        gateway_address = "1.2.3.4/24"
        route_1_network = "172.250.0.0/16"
        route_1_gateway = "192.168.250.3"
        route_2_network = "172.250.1.0/16"
        route_2_gateway = "192.168.250.4"
        routes = [
            {"network": route_1_network, "gateway": route_1_gateway},
            {"network": route_2_network, "gateway": route_2_gateway},
        ]
        relation_data = {
            "name": interface_name,
            "gateway": gateway_address,
            "routes": json.dumps(routes),
        }

        relation_id = self.harness.add_relation(
            relation_name="router", remote_app="router-requirer"
        )
        self.harness.add_relation_unit(
            relation_id=relation_id, remote_unit_name="router-requirer/0"
        )
        self.harness.update_relation_data(
            relation_id=relation_id, app_or_unit="router-requirer/0", key_values=relation_data
        )

        patch_exec.assert_any_call(
            command=["/bin/bash", "-c", f"ip route add {route_1_network} via {route_1_gateway}"]
        )
        patch_exec.assert_any_call(
            command=["/bin/bash", "-c", f"ip route add {route_2_network} via {route_2_gateway}"]
        )
