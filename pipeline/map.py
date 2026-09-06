"""The existing supervision map, projected from the compiled LangGraphs.

Only the human/orchestrator loop is synthetic. Graph plumbing is folded into
display nodes; specialist membership and sequencing come from actual edges.

`specialists_done` is DRAWN, not folded away. It is a pure join — the barrier
the peer fan-out lands on — and hiding it made `destinations()` recurse
through it and surface both of its conditional targets on every specialist.
The map then showed eleven specialists each reporting straight back to the
orchestrator and straight into control assurance, when in truth there is one
edge out of one shared barrier. That contradicted the architecture the whole
submission rests on (agents never message each other or the orchestrator;
everything lands on the ledger), so the join stays visible.
"""
from agents.catalog import AGENTS, PEERS

ALIASES = {
    'ingest': 'orchestrator', 'dispatch': 'orchestrator',
    'load_context': 'orchestrator', 'orchestrate': 'orchestrator', 'record': 'orchestrator',
    'risk_score': 'orchestrator', 'load_record': 'draft_report', 'critic': 'findings',
}
LABELS = {'kya': 'KYA', 'control_assurance': 'Control Assurance',
          'findings': 'Facts / Assessments', 'human_gate': 'Decision / Sign-off',
          'specialists_done': 'All Specialists In'}


def supervision_map(graphs):
    nodes = {'supervisor': dict(id='supervisor', label='Supervisor', lane='hub', synthetic=True, role='hub')}
    edges = {}
    def add_edge(source, target, kind='main'):
        if source != target:
            edges[(source, target)] = dict(source=source, target=target, kind=kind)

    for kind, compiled in graphs.items():
        graph = compiled.get_graph()
        visible = {n: ALIASES.get(n, n) for n in graph.nodes if not n.startswith('__')}
        for original, name in visible.items():
            role = ('peer' if original in PEERS else 'control' if original == 'control_assurance'
                    else 'join' if original == 'specialists_done'
                    else 'on_request' if original in ('investigator', 'systemic') else 'support')
            nodes.setdefault(name, dict(id=name, label=LABELS.get(name, name.replace('_', ' ').title()),
                                       lane='hub' if name == 'orchestrator' else kind,
                                       synthetic=name not in graph.nodes, role=role))
        def destinations(start, seen):
            for edge in graph.edges:
                if edge.source != start or edge.target in seen or edge.target.startswith('__'):
                    continue
                if edge.target in visible:
                    yield edge.target
                else:
                    yield from destinations(edge.target, seen | {edge.target})
        for original, source in visible.items():
            for target_id in destinations(original, {original}):
                target = visible[target_id]
                edge_kind = ('return' if target == 'orchestrator' else
                             'loop' if original == 'grounding_check' and target == 'draft_report' else
                             'route' if target_id in ('investigator', 'systemic') else 'main')
                add_edge(source, target, edge_kind)
    add_edge('supervisor', 'orchestrator')
    add_edge('orchestrator', 'supervisor', 'return')
    add_edge('orchestrator', 'draft_report', 'route')
    return dict(nodes=list(nodes.values()), edges=list(edges.values()))
