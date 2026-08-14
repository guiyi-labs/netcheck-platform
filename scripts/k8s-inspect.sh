#!/usr/bin/env bash
# ============================================================
# Kubernetes 集群巡检：从 K8s API 采集节点/工作负载/Pod 状态并输出 JSON。
# 供「容器/K8s 巡检扩展（D3）」使用：可在集群内以 kubectl 运行，
# 也可作为 netcheck 的外部数据源，将 JSON 结果导入平台。
#
# 依赖：kubectl 且在集群上下文内，或提供 KUBECONFIG。
# 用法：./scripts/k8s-inspect.sh [namespace] > k8s_snapshot.json
# ============================================================
set -euo pipefail

NS="${1:-}"

kubectl_cmd() {
  if [ -n "$NS" ]; then
    kubectl -n "$NS" "$@"
  else
    kubectl --all-namespaces "$@"
  fi
}

# 节点状态
NODES=$(kubectl get nodes -o json 2>/dev/null)
# Pod 状态统计（含 namespace 维度）
PODS=$(kubectl_cmd get pods -o json 2>/dev/null)

# 只读快照：gzip 原文太长，此处仅提取关键字段
python3 - "$NODES" "$PODS" "$NS" <<'PY'
import json, sys
nodes_raw, pods_raw, ns = sys.argv[1], sys.argv[2], sys.argv[3] or "all"

out = {"namespace": ns, "nodes_total": 0, "nodes_not_ready": [], "pods_total": 0, "pods_not_running": [], "nodes_by_role": {}}
try:
    nodes = json.loads(nodes_raw)["items"]
    out["nodes_total"] = len(nodes)
    for n in nodes:
        name = n["metadata"]["name"]
        labels = n.get("metadata", {}).get("labels", {})
        role = labels.get("kubernetes.io/role") or labels.get("node-role.kubernetes.io/control-plane")
        if role:
            out["nodes_by_role"].setdefault(role, 0)
            out["nodes_by_role"][role] += 1
        for cond in n.get("status", {}).get("conditions", []):
            if cond.get("type") == "Ready" and cond.get("status") != "True":
                out["nodes_not_ready"].append(name)
except Exception:
    pass

try:
    pods = json.loads(pods_raw)["items"]
    out["pods_total"] = len(pods)
    ns_count = {}
    for p in pods:
        metadata = p.get("metadata", {})
        pns = metadata.get("namespace", "?")
        ns_count[pns] = ns_count.get(pns, 0) + 1
        phase = (p.get("status") or {}).get("phase")
        if phase and phase not in ("Running", "Succeeded"):
            out["pods_not_running"].append({"namespace": pns, "name": metadata.get("name"), "phase": phase})
    out["pods_by_namespace"] = ns_count
except Exception:
    pass

print(json.dumps(out, ensure_ascii=False, indent=2))
PY