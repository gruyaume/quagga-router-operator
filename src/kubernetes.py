# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Kubernetes specific utilities."""

import json
import logging
from typing import Dict, List

import httpx
from lightkube import Client
from lightkube.core.exceptions import ApiError
from lightkube.generic_resource import create_namespaced_resource
from lightkube.models.core_v1 import Capabilities
from lightkube.models.meta_v1 import ObjectMeta
from lightkube.resources.apps_v1 import StatefulSet
from lightkube.types import PatchType

logger = logging.getLogger(__name__)

NETWORK_ATTACHMENT_DEFINITION_NAME = "router-net"

NetworkAttachmentDefinition = create_namespaced_resource(
    group="k8s.cni.cncf.io",
    version="v1",
    kind="NetworkAttachmentDefinition",
    plural="network-attachment-definitions",
)


class Kubernetes:
    """Kubernetes main class."""

    def __init__(self, namespace: str, statefulset_name: str):
        """Initializes K8s client."""
        self.client = Client()
        self.namespace = namespace
        self.statefulset_name = statefulset_name

    def create_network_attachment_definition(self) -> None:
        """Creates network attachment definitions.

        Returns:
            None
        """
        if not self.network_attachment_definition_created(name=NETWORK_ATTACHMENT_DEFINITION_NAME):
            access_interface_config = {
                "cniVersion": "0.3.1",
                "type": "macvlan",
                "ipam": {"type": "static"},
            }
            access_interface_spec = {"config": json.dumps(access_interface_config)}
            network_attachment_definition = NetworkAttachmentDefinition(
                metadata=ObjectMeta(name=NETWORK_ATTACHMENT_DEFINITION_NAME),
                spec=access_interface_spec,
            )
            self.client.create(obj=network_attachment_definition, namespace=self.namespace)  # type: ignore[call-overload]  # noqa: E501
            logger.info(
                f"NetworkAttachmentDefinition {NETWORK_ATTACHMENT_DEFINITION_NAME} created"
            )

    def network_attachment_definition_created(self, name: str) -> bool:
        """Returns whether a NetworkAttachmentDefinition is created."""
        try:
            self.client.get(
                res=NetworkAttachmentDefinition,
                name=name,
                namespace=self.namespace,
            )
            logger.info(f"NetworkAttachmentDefinition {name} already created")
            return True
        except ApiError as e:
            if e.status.reason == "NotFound":
                logger.info(f"NetworkAttachmentDefinition {name} not yet created")
                return False
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.error(
                    "NetworkAttachmentDefinition resource not found."
                    "You may need to install Multus CNI."
                )
                raise
            logger.info("Unexpected error while checking NetworkAttachmentDefinition")
            return False
        return False

    def add_security_context_to_statefulset(self) -> None:
        """Adds security context to the statefulset."""
        if self.security_context_is_patched():
            return
        statefulset = self.client.get(
            res=StatefulSet, name=self.statefulset_name, namespace=self.namespace
        )
        if not hasattr(statefulset, "spec"):
            raise RuntimeError("Could not find `spec` in the statefulset")
        statefulset.spec.template.spec.containers[1].securityContext.privileged = True
        statefulset.spec.template.spec.containers[1].securityContext.capabilities = Capabilities(
            add=[
                "NET_ADMIN",
            ]
        )
        self.client.patch(
            res=StatefulSet,
            name=self.statefulset_name,
            obj=statefulset,
            patch_type=PatchType.MERGE,
            namespace=self.namespace,
        )
        logger.info("Security Context patched in statefulset")

    def add_multus_annotation_to_statefulset(self, interface_name: str, ips: List[str]) -> None:
        """Adds a multus annotation to the statefulset."""
        annotation = {
            "name": NETWORK_ATTACHMENT_DEFINITION_NAME,
            "interface": interface_name,
            "ips": ips,
        }
        if self.annotation_is_added_to_statefulset(annotation=annotation):
            return
        statefulset = self.client.get(
            res=StatefulSet, name=self.statefulset_name, namespace=self.namespace
        )
        if not hasattr(statefulset, "spec"):
            raise RuntimeError("Could not find `spec` in the statefulset")

        statefulset.spec.template.metadata.annotations["k8s.v1.cni.cncf.io/networks"].append(
            annotation
        )
        self.client.patch(
            res=StatefulSet,
            name=self.statefulset_name,
            obj=statefulset,
            patch_type=PatchType.MERGE,
            namespace=self.namespace,
        )

    def annotation_is_added_to_statefulset(self, annotation: Dict) -> bool:
        """Returns whether a given annotation is in the statefulset."""
        statefulset = self.client.get(
            res=StatefulSet, name=self.statefulset_name, namespace=self.namespace
        )
        if not hasattr(statefulset, "spec"):
            return False
        if "k8s.v1.cni.cncf.io/networks" not in statefulset.spec.template.metadata.annotations:
            logger.info("Multus annotation not yet added to statefulset")
            return False
        if (
            annotation
            not in statefulset.spec.template.metadata.annotations["k8s.v1.cni.cncf.io/networks"]
        ):
            return False
        return True

    def security_context_is_patched(self) -> bool:
        """Returns whether the statefulset security context is patched."""
        statefulset = self.client.get(
            res=StatefulSet, name=self.statefulset_name, namespace=self.namespace
        )
        if not hasattr(statefulset, "spec"):
            return False
        if not statefulset.spec.template.spec.containers[1].securityContext.privileged:
            return False
        if (
            "NET_ADMIN"
            not in statefulset.spec.template.spec.containers[1].securityContext.capabilities.add
        ):
            return False
        return True

    def delete_network_attachment_definition(self) -> None:
        """Deletes network attachment definitions.

        Returns:
            None
        """
        if self.network_attachment_definition_created(name=NETWORK_ATTACHMENT_DEFINITION_NAME):
            self.client.delete(
                res=NetworkAttachmentDefinition,
                name=NETWORK_ATTACHMENT_DEFINITION_NAME,
                namespace=self.namespace,
            )
            logger.info(
                f"NetworkAttachmentDefinition {NETWORK_ATTACHMENT_DEFINITION_NAME} deleted"
            )
