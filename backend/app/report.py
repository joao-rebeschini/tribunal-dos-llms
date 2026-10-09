"""Exportação da audiência salva para Markdown em português, sem novas chamadas externas."""

def report(match, events):
    """Monta Markdown a partir da partida e dos eventos, incluindo avisos, fontes e julgamento disponível."""
    lines = ['# Tribunal dos LLMs', '', f"**Pergunta:** {match['question']}",
             f"**Modo:** {'Demonstração pré-gravada, com conteúdo ilustrativo' if match['demo'] else 'Debate real'}",
             f"**Estado:** {match['status']}", '**Avaliação:** julgamento automatizado.', '']
    if not match['demo']:
        lines += ['## Modelos selecionados'] + [f'- {role}: {model}' for role, model in match['models'].items()] + ['']
        actuals = {(e['data']['role'], e['data']['actual']) for e in events if e['type'] == 'model'}
        lines += ['## Modelos efetivamente utilizados'] + [f'- {r}: {m}' for r, m in sorted(actuals)] + ['']
    for e in events:
        d = e['data']
        if e['type'] == 'speech':
            lines += [f"### Rodada {d['round']} · {d['role']} · {d['phase']}", d['text'], '']
        elif e['type'] == 'evidence':
            lines += [f"**{d['status']} · {d['role']}:** {d['claim']}", d['explanation']]
            lines += [f"- [{s['title']}]({s['url']})" for s in d['sources']]
            lines += ['']
        elif e['type'] in ('warning', 'interrupted', 'cancelled'):
            lines += [f"**Aviso:** {d['message']}", '']
    result = match['result']
    if result:
        lines += ['## Julgamento automatizado', result['conclusion'], result['justification'],
                  f"Consenso: {'sim' if result['consensus'] else 'não'}; rodadas: {result['rounds']}.", '',
                  '| Papel | Evidências | Coerência | Refutações | Média |', '|---|---:|---:|---:|---:|']
        for role, s in result['scores'].items():
            lines += [f"| {role} | {s['evidencias']} | {s['coerencia']} | {s['refutacoes']} | {s['final']} |"]
        lines += ['', '### Divergências'] + [f'- {d}' for d in result['divergences']]
        lines += ['', '### Afirmações contraditas por evidências']
        for role, claims in result['contradicted'].items():
            lines += [f"- {role}: {len(claims)}"] + [f"  - {c['claim']}: {c['explanation']}" for c in claims]
        lines += ['', 'Ausência de fontes não é contada automaticamente como alucinação.']
    return '\n'.join(lines) + '\n'
