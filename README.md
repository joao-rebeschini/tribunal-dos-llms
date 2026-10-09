# Tribunal dos LLMs

Uma pergunta, quatro perspectivas. Aplicação local de portfólio com tribunal em pixel art original, debate estruturado e fontes ligadas às afirmações. Interface e relatórios em português brasileiro, UTF-8.

## Executar

Requisitos: Python 3.11 ou superior, Node.js 20.19 ou superior e pnpm 11.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
Copy-Item .env.example .env
cd ..\frontend
pnpm install --frozen-lockfile
pnpm build
cd ..\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abra <http://127.0.0.1:8000>. O backend serve o frontend compilado. A demonstração pré-gravada não precisa de chaves e não consome APIs. Falas, notas e classificação da demonstração são conteúdo editorial ilustrativo, identificado na tela e no relatório.

Em macOS/Linux, use `python3`, `.venv/bin/python` e `cp .env.example .env`. Para desenvolvimento, inicie o backend e, em outro terminal, execute `pnpm dev` na pasta `frontend`; abra o endereço local informado pelo Vite. O proxy encaminha `/api` ao backend.

## Configurar debates reais

Edite apenas `backend/.env`:

```dotenv
OPENROUTER_API_KEY=sua_chave
TAVILY_API_KEY=sua_chave
TAVILY_MONTHLY_BUDGET=1000
```

- Crie uma chave no [OpenRouter](https://openrouter.ai/settings/keys). O catálogo ao vivo é filtrado por preços zero de entrada, saída e demais taxas declaradas. Modelos sem saída de texto são excluídos. O preço é revalidado antes de cada chamada. A aplicação envia tetos de preço zero, não habilita plugins pagos nem fallback de modelos. Registra o ID solicitado e o ID efetivamente retornado; o sufixo `:free` pode ser omitido pelo provedor na resposta.
- Crie uma chave no [Tavily](https://app.tavily.com), em conta Free sem cobrança por uso habilitada. O backend consulta `/usage` antes de cada nova pesquisa e bloqueia planos pagos, Pay As You Go habilitado, cota esgotada ou dados de faturamento indisponíveis. Busca basic custa um crédito; parâmetros automáticos estão desativados. Há reserva mensal local em SQLite e cache de 24 horas. A aplicação não altera o faturamento da conta. Prefira uma conta exclusiva gratuita: outros aplicativos podem consumir a mesma franquia.
- Reinicie o backend após alterar o `.env`. As chaves não vão para o navegador, transcrição ou Git. Não coloque segredos na pergunta.

Os limites e a disponibilidade gratuita variam. Consulte [limites do OpenRouter](https://openrouter.ai/docs/api_reference/limits), [preços do Tavily](https://www.tavily.com/pricing), [Tavily Usage](https://docs.tavily.com/documentation/api-reference/endpoint/usage) e [roteamento de provedores](https://openrouter.ai/docs/guides/routing/provider-selection).

## Como funciona

1. Defesa apresenta ou aprimora sua posição.
2. Oposição responde e refuta.
3. Verificador extrai até três fatos da rodada, pesquisa e classifica cada um como confirmado, contradito ou inconclusivo. Opiniões não viram fatos.
4. Juiz propõe uma conclusão comum.
5. Ambos aceitam ou rejeitam explicitamente a mesma conclusão.
6. Se ambos aceitarem o texto idêntico, o juiz confirma que ele responde à pergunta.

Consenso confirmado encerra cedo. Uma única rejeição, conclusão diferente ou confirmação negativa impede encerramento antecipado. Depois de cinco rodadas, o juiz emite o julgamento mesmo com divergências. Cada fala tem até 180 palavras, validada no backend. Condições e soluções híbridas são permitidas.

O juiz recebe falas e fontes, sem identificar os modelos dos debatedores. A avaliação é apresentada como julgamento automatizado. Evidências, coerência e refutações recebem notas de 0 a 10; a nota final é a média simples. A contagem de afirmações contraditas é calculada pelas verificações com fontes e fica separada do placar. Ausência de fontes não conta automaticamente como alucinação. A classificação das fontes também é automatizada e pode errar.

## Acompanhar as falas

Antes de iniciar uma audiência, o backend consulta o contador diário de requisições gratuitas do OpenRouter. A tela exibe o restante da franquia e a renovação prevista à meia-noite UTC, no horário do navegador. Com zero requisições, a partida não é criada e a demonstração continua disponível. Uma audiência usa várias chamadas; tentativas de geração também usam a franquia. O limite diário da conta é diferente de saldo ou limite de gastos da chave, e trocar de modelo não renova essa franquia. Use **Atualizar limites** para consultar novamente.

A apresentação usa uma fila independente da execução dos agentes. Por padrão, o texto aparece aos poucos e cada fala espera você clicar em **Próxima fala**. **Mostrar fala completa** revela o restante da fala atual; **Pausar**, **Automático** e as velocidades de 0,5×, 1× e 2× controlam a leitura. **Ver tudo** abre os eventos já recebidos, e **Rever** reinicia a apresentação da audiência salva. O julgamento só aparece ao chegar à sua posição na fila.

O balão fica ligado ao personagem que está falando, que dá um pequeno passo à frente. O registro lateral acompanha o mesmo texto progressivo. A pausa afeta apenas a apresentação: os agentes continuam executando e o backend preserva os eventos. Para interromper as chamadas, use **Cancelar**.

Esta versão usa revelação progressiva depois da validação da resposta completa. Ela não transmite tokens do modelo enquanto ele gera o JSON. A interface identifica esse comportamento como texto progressivo; falas inválidas ou raciocínio interno não são apresentados como argumentos.

## Arquitetura

```text
React + TypeScript + Vite
    │ REST + EventSource/SSE
FastAPI (um processo local)
    │ tarefas asyncio canceláveis
LangGraph StateGraph → stream customizado → eventos SQLite → SSE
    ├─ OpenRouter: falas e JSON validado com Pydantic
    └─ Tavily: pesquisa basic e cache
SQLite: partidas, eventos, modelos reais, fontes, resultados, cache e orçamento
```

`backend/app/engine.py` concentra as regras do debate. `providers.py` implementa as integrações e os bloqueios de custo. `storage.py` persiste os dados. `main.py` gerencia tarefas e API. `fixtures/demo.json` contém a partida pré-gravada. O cenário e os sprites são elementos CSS; as falas são texto selecionável. Animações respeitam `prefers-reduced-motion`.

Cada evento recebe número sequencial por partida em transação SQLite. Na reconexão, SSE aceita `Last-Event-ID` e `after`; o frontend também elimina duplicatas. Cancelamento interrompe a tarefa, preserva eventos e não cria julgamento. Reinício marca partidas em andamento como interrompidas. Não há retomada automática do debate nem checkpointer de conversa nesta versão; é possível rever/exportar o progresso e iniciar nova partida.

## API

| Método | Endpoint | Função |
|---|---|---|
| GET | `/api/health` | Estado do backend e presença de configuração, sem segredos |
| GET | `/api/models` | Catálogo atual de modelos gratuitos |
| GET | `/api/limits` | Contador diário de requisições gratuitas e renovação prevista, sem dados da chave |
| POST | `/api/matches` | Criar partida: `question`, `models` para os quatro papéis |
| POST | `/api/demo` | Reproduzir demonstração gratuita |
| GET | `/api/matches` | Histórico das 100 partidas mais recentes |
| GET | `/api/matches/{id}` | Partida, resultado e todos os eventos |
| GET | `/api/matches/{id}/events` | SSE com replay e reconexão |
| POST | `/api/matches/{id}/cancel` | Cancelar e preservar progresso |
| GET | `/api/matches/{id}/report` | Exportar Markdown UTF-8 |

Documentação interativa: <http://127.0.0.1:8000/docs>.

## Validação

Os testes da fila de leitura usam o suporte nativo a TypeScript do Node.js 22.6 ou superior.

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
cd ..\frontend
pnpm build
pnpm test
```

Testes simulam as APIs, sem gastar cotas: consenso, uma única discordância, confirmação do juiz, limite de rodadas, fontes, pesquisa indisponível, preços pagos, cota, cancelamento, reconexão SSE, histórico, exportação e recuperação após reinício. Também cobrem respostas vazias, raciocínio sem fala, JSON no formato incorreto, recusas e campos de faturamento nulos. As chamadas reais de defesa, oposição e extração de afirmações foram verificadas durante a depuração; disponibilidade e limites externos podem impedir o julgamento completo.

Se um modelo consumir a geração em raciocínio e retornar uma fala vazia, o backend aumenta o limite e tenta novamente, até três chamadas. Quando permitido pelo catálogo, o raciocínio opcional é desativado. O raciocínio interno nunca é usado como fala. Se o formato JSON estiver incorreto, a próxima tentativa recebe os erros de validação. Erros persistentes preservam o histórico e exibem uma mensagem específica.

Um erro 429 do OpenRouter indica limite de requisições ou capacidade: aguarde ou escolha outro modelo gratuito e inicie uma nova partida. No Tavily, `paygo_limit: null` é aceito somente quando o plano gratuito, o consumo e a franquia são confirmados e ainda existe um crédito inteiro dentro da franquia e do teto local de 1.000 créditos. O campo não é convertido em zero nem autoriza uso pago. Ausência de dados de consumo ou franquia, consumo pago, planos pagos e cota esgotada continuam bloqueando buscas. Falhas HTTP distinguem chave recusada (401), limite de requisições (429) e indisponibilidade da consulta de cota.

Na validação dessa integração, uma busca real retornou três fontes. Os testes também verificam que o tribunal preserva cada classificação do verificador: confirmada, contradita ou inconclusiva, com suas fontes. Falha de pesquisa continua produzindo inconclusão, sem evidência inventada.

## Limitações da primeira versão

Execução local, um único processo Uvicorn, sem login, hospedagem, Supabase, RAG ou banco vetorial. Não execute múltiplos workers, pois as tarefas vivem no processo. Tentativas de inferência são limitadas a três para rede, 5xx e JSON inválido; cotas interrompem imediatamente. Pesquisas não repetem POST incerto, para não duplicar consumo. Erros de pesquisa produzem inconclusão, nunca fontes fictícias. A aplicação não garante a verdade de um julgamento de LLM.

Licença MIT. Cenário e sprites originais do projeto; ícones Lucide sob licença ISC.
