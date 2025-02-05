from base64 import b64decode

import waiting
from kubernetes.client import ApiClient, CoreV1Api, CustomObjectsApi, V1NodeList

from assisted_test_infra.test_infra import utils
from assisted_test_infra.test_infra.helper_classes.kube_helpers import Secret, create_kube_api_client
from service_client import log

HYPERSHIFT_DIR = "build/hypershift/"
DEFAULT_WAIT_FOR_NODES_TIMEOUT = 10 * 60


class HyperShift:
    """
    Hypershift resource that allow interaction with hypershift CLI, nodepool and hypershift cluster kubeapi-server.
    """

    NODEPOOL_NAMESPACE = "clusters"
    NODEPOOL_PLOURAL = "nodepools"
    HYPERSHIFT_API_GROUP = "hypershift.openshift.io"
    HYPERSHIFT_API_VERSION = "v1alpha1"

    def __init__(self, name: str):
        self.name = name
        self.kubeconfig_path = ""
        self.hypershift_cluster_client = None

    def create(self, pull_secret_file: str, agent_namespace: str, provider_image: str = "", ssh_key: str = ""):
        log.info(f"Creating HyperShift cluster {self.name}")
        cmd = (
            f"./bin/hypershift create cluster agent --pull-secret {pull_secret_file} --name {self.name}"
            f" --agent-namespace {agent_namespace}"
        )
        if provider_image:
            log.info(f"Using provider image {provider_image}")
            cmd += f" --annotations hypershift.openshift.io/capi-provider-agent-image={provider_image}"
        if ssh_key:
            cmd += f" --ssh-key {ssh_key}"
        utils.run_command_with_output(cmd, cwd=HYPERSHIFT_DIR)

    def delete(self):
        log.info(f"Deleting HyperShift cluster {self.name}")
        utils.run_command_with_output(f"./bin/hypershift destroy cluster agent --name {self.name}", cwd=HYPERSHIFT_DIR)

    def dump(self, output_folder, kubeconfig_path=None):
        log.info(f"Dump HyperShift cluster {self.name} to {output_folder}")
        utils.run_command_with_output(
            f"KUBECONFIG={kubeconfig_path} {HYPERSHIFT_DIR}/bin/hypershift dump cluster --name {self.name} "
            f"--artifact-dir {output_folder}"
        )

    def download_kubeconfig(self, kube_api_client: ApiClient) -> str:
        log.info(f"Downloading kubeconfig for HyperShift cluster {self.name}")
        kubeconfig_data = (
            Secret(
                kube_api_client=kube_api_client,
                namespace=f"clusters-{self.name}",
                name="admin-kubeconfig",
            )
            .get()
            .data["kubeconfig"]
        )
        hypershift_kubeconfig_path = utils.get_kubeconfig_path(self.name) + "-hypershift"

        log.info(f"Kubeconfig path {hypershift_kubeconfig_path}")
        with open(hypershift_kubeconfig_path, "wt") as kubeconfig_file:
            kubeconfig_file.write(b64decode(kubeconfig_data).decode())
            kubeconfig_file.flush()
        self.kubeconfig_path = hypershift_kubeconfig_path
        return self.kubeconfig_path

    def set_nodepool_node_count(self, kube_api_client: ApiClient, node_count: int) -> None:
        log.info(f"Setting HyperShift cluster {self.name} node count to: {node_count}")
        crd_api = CustomObjectsApi(kube_api_client)
        node_count = node_count
        body = {"spec": {"nodeCount": node_count}}
        crd_api.patch_namespaced_custom_object(
            group=HyperShift.HYPERSHIFT_API_GROUP,
            version=HyperShift.HYPERSHIFT_API_VERSION,
            plural=HyperShift.NODEPOOL_PLOURAL,
            name=self.name,
            namespace=HyperShift.NODEPOOL_NAMESPACE,
            body=body,
        )

    def get_nodes(self, ready: bool = False) -> V1NodeList:
        if self.hypershift_cluster_client is None:
            hypershift_cluter_kubeapi_client = create_kube_api_client(self.kubeconfig_path)
            self.hypershift_cluster_client = CoreV1Api(hypershift_cluter_kubeapi_client)
        nodes = self.hypershift_cluster_client.list_node()
        if ready:
            return filterNodeByReadyStatus(nodes)
        return nodes

    def wait_for_nodes(self, node_count: int, ready: bool = False) -> V1NodeList:
        def _sufficient_nodes() -> bool:
            return len(self.get_nodes(ready).items) == node_count

        return waiting.wait(
            lambda: _sufficient_nodes(),
            sleep_seconds=1,
            timeout_seconds=DEFAULT_WAIT_FOR_NODES_TIMEOUT,
            waiting_for="nodes to join the hypershift cluster",
        )
        # TODO: validate the nodes ready condition


def filterNodeByReadyStatus(nodes: V1NodeList) -> V1NodeList:
    filtered_items = []
    for node in nodes.items:
        for condition in node.status.conditions:
            # if the node is ready add it to the return list
            if condition.type == "Ready" and condition.status == "True":
                filtered_items.append(node)
    nodes.items = filtered_items
    return nodes
