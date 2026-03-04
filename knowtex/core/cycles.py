"""Cycle detection using Tarjan's SCC algorithm (iterative)."""

from collections import defaultdict


def find_cycles(edges):
    """Find all edges that participate in cycles using Tarjan's SCC algorithm.

    Returns set of (source, target) keys for edges in cycles.
    Uses an iterative (explicit call stack) approach to avoid RecursionError.
    """
    adj = defaultdict(list)
    all_nodes = set()
    for e in edges:
        adj[e.source].append(e.target)
        all_nodes.add(e.source)
        all_nodes.add(e.target)

    idx_counter = 0
    scc_stack = []
    on_stack = set()
    index = {}
    lowlink = {}
    sccs = []

    for root in all_nodes:
        if root in index:
            continue
        call_stack = [(root, iter(adj.get(root, [])), True)]
        while call_stack:
            v, neighbors, is_init = call_stack[-1]
            if is_init:
                index[v] = idx_counter
                lowlink[v] = idx_counter
                idx_counter += 1
                scc_stack.append(v)
                on_stack.add(v)
                call_stack[-1] = (v, neighbors, False)

            pushed_child = False
            for w in neighbors:
                if w not in index:
                    call_stack.append((w, iter(adj.get(w, [])), True))
                    pushed_child = True
                    break
                elif w in on_stack:
                    lowlink[v] = min(lowlink[v], index[w])

            if pushed_child:
                continue

            if lowlink[v] == index[v]:
                scc = []
                while True:
                    w = scc_stack.pop()
                    on_stack.discard(w)
                    scc.append(w)
                    if w == v:
                        break
                if len(scc) > 1:
                    sccs.append(set(scc))

            call_stack.pop()
            if call_stack:
                parent = call_stack[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[v])

    edge_set = {e.key() for e in edges}
    cycle_edge_keys = set()
    for scc in sccs:
        for src in scc:
            for tgt in adj[src]:
                if tgt in scc and (src, tgt) in edge_set:
                    cycle_edge_keys.add((src, tgt))

    return cycle_edge_keys
