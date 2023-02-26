# Copyright 2022 Guillaume Belanger
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, patch

from ops import testing
from ops.model import ActiveStatus

from charm import QuaggaOperatorCharm


class TestCharm(unittest.TestCase):
    @patch("lightkube.core.client.GenericSyncClient")
    def setUp(self, patch_k8s_client):
        self.namespace = "whatever"
        self.harness = testing.Harness(QuaggaOperatorCharm)
        self.harness.set_model_name(name=self.namespace)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @patch("kubernetes.Kubernetes.create_network_attachment_definition")
    @patch("kubernetes.Kubernetes.patch_statefulset")
    def test_given_when_on_install_then_multus_network_attachment_definition_is_created(
        self, patch_create_network_attachment_definition, patch_patch_statefulset
    ):
        self.harness.charm.on.install.emit()

        patch_create_network_attachment_definition.assert_called()
        patch_patch_statefulset.assert_called()

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
        self.harness.container_pebble_ready(container_name="quagga")

        expected_plan = {
            "services": {
                "quagga": {
                    "startup": "enabled",
                    "override": "replace",
                    "command": "sleep infinity",
                }
            }
        }

        updated_plan = self.harness.get_container_pebble_plan("quagga").to_dict()

        self.assertEqual(expected_plan, updated_plan)

    @patch("ops.model.Container.exec", new=Mock())
    def test_given_when_pebble_ready_then_status_is_active(self):
        self.harness.container_pebble_ready("quagga")

        self.assertEqual(self.harness.model.unit.status, ActiveStatus())
