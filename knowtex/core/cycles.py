"""Cycle detection using Tarjan's SCC algorithm (iterative)."""

from collections import defaultdict


def strongly_connected_components(edges):
    """Tarjan's SCC algorithm (iterative, so deep graphs cannot overflow
    the Python stack).

    Returns (sccs, adj): the list of all SCCs as sets (singletons
    included) and the adjacency dict used to compute them.
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
                sccs.append(set(scc))

            call_stack.pop()
            if call_stack:
                parent = call_stack[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[v])

    return sccs, adj


def find_cycles(edges):
    """Find all edges that participate in cycles.

    Returns set of (source, target) keys for edges in cycles.
    """
    sccs, adj = strongly_connected_components(edges)
    edge_set = {e.key() for e in edges}
    cycle_edge_keys = set()
    for scc in sccs:
        if len(scc) < 2:
            continue
        for src in scc:
            for tgt in adj[src]:
                if tgt in scc and (src, tgt) in edge_set:
                    cycle_edge_keys.add((src, tgt))

    return cycle_edge_keys


def transitive_reduction(edges):
    """Return the edges with transitively redundant ones removed.

    An edge u -> v is redundant when v is reachable from u through a
    path of length >= 2 that does not use the edge itself (so successors
    inside the source's own cycle are not followed).  Reachability
    is computed on the condensation of the graph (one vertex per
    strongly connected component), where memoized descendant sets are
    exact; a node's descendants are all members of the components
    reachable from its own component, plus the other members of its own
    component.  Edges inside a cycle are always kept.
    Pure Python; no Graphviz needed (used by the CLI and the web build).
    """
    sccs, _ = strongly_connected_components(edges)
    comp_of = {}
    for i, scc in enumerate(sccs):
        for n in scc:
            comp_of[n] = i
    adj = defaultdict(set)
    cadj = defaultdict(set)           # condensation DAG
    for e in edges:
        adj[e.source].add(e.target)
        cu, cv = comp_of[e.source], comp_of[e.target]
        if cu != cv:
            cadj[cu].add(cv)

    cdesc = {}                        # component -> frozenset of reachable components

    def comp_descendants(root):
        if root in cdesc:
            return cdesc[root]
        stack = [(root, iter(cadj[root]))]
        seen = {root}
        while stack:
            comp, it = stack[-1]
            advanced = False
            for child in it:
                if child in cdesc or child in seen:
                    continue
                seen.add(child)
                stack.append((child, iter(cadj[child])))
                advanced = True
                break
            if advanced:
                continue
            acc = set()
            for child in cadj[comp]:
                acc.add(child)
                acc |= cdesc[child]
            cdesc[comp] = frozenset(acc)
            stack.pop()
        return cdesc[root]

    def reachable(u, v):
        """Is v reachable from u by a path of length >= 1?"""
        cu, cv = comp_of[u], comp_of[v]
        if cu == cv:
            return len(sccs[cu]) > 1
        return cv in comp_descendants(cu)

    cycle_keys = find_cycles(edges)
    kept = []
    for e in edges:
        if e.key() in cycle_keys:
            kept.append(e)
            continue
        # A path through a successor w that sits in the source's own cycle
        # could come back through the edge being tested, so only successors
        # in other components count.
        cu = comp_of[e.source]
        redundant = any(w != e.target and comp_of[w] != cu
                        and reachable(w, e.target)
                        for w in adj[e.source])
        if not redundant:
            kept.append(e)
    return kept
