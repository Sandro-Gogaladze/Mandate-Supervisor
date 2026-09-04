"""The existing supervision map, projected from the compiled LangGraphs.

Only the human/orchestrator loop is synthetic. Graph plumbing is folded into
display nodes; specialist membership and sequencing come from actual edges.
"""
from agents.catalog import AGENTS, PEERS

ALIASES = {
    'ingest': 'orchestrator', 'dispatch': 'orchestrator',
    'load_context': 'orchestrator', 'orchestrate': 'orchestrator', 'record': 'orchestrator',
    'risk_score': 'orchestrator', 'load_record': 'draft_report', 'critic': 'findings',
}
LABELS = {'kya': 'KYA', 'control_assurance': 'Control Assurance',
          'findings': 'Facts / Assessments', 'human_gate': 'Decision / Sign-off'}


def supervision_map(graphs):
    nodes = {'supervisor': dict(id='supervisor', label='Supervisor', lane='hub', synthetic=True, role='hub')}
    edges = {}
    def add_edge(source, target, kind='main'):
        if source != target:
            edges[(source, target)] = dict(source=source, target=target, kind=kind)

    for kind, compiled in graphs.items():
        graph = compiled.get_graph()
        visible = {n: ALIASES.get(n, n) for n in graph.nodes
                   if not n.startswith('__') and n != 'specialists_done'}
        for original, name in visible.items():
            role = ('peer' if original in PEERS else 'control' if original == 'control_assurance'
                    else 'on_request' if original in ('investigator', 'systemic', 'red_team') else 'support')
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
                             'route' if target_id in ('investigator', 'systemic', 'red_team') else 'main')
                add_edge(source, target, edge_kind)
    add_edge('supervisor', 'orchestrator')
    add_edge('orchestrator', 'supervisor', 'return')
    add_edge('orchestrator', 'draft_report', 'route')
    return dict(nodes=list(nodes.values()), edges=list(edges.values()))
