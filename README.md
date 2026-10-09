# Tribunal dos LLMs

Uma pergunta, quatro perspectivas. Aplicação local de portfólio com tribunal em pixel art original, debate estruturado e fontes ligadas às afirmações. Interface e relatórios em português brasileiro, UTF-8.

## Navegação

- [Instalação e execução](#executar)
- [Configuração das APIs](#configurar-debates-reais)
- [Regras do debate](#como-funciona)
- [Leitura e reprodução](#acompanhar-as-falas)
- [Arquitetura](#arquitetura) e [API](#api)
- [Testes](#validação), [diagnóstico](#diagnóstico-de-problemas) e [contribuição](#alterar-o-projeto)
- [Guia de todos os arquivos](docs/ARQUIVOS.md)
- [Contratos, eventos e persistência](docs/ARQUITETURA.md)
- [Todos os prompts e formatos de resposta](docs/PROMPTS.md)

## O que você pode fazer

Escrever uma pergunta, escolher um modelo gratuito para cada papel e acompanhar uma audiência de até cinco rodadas. O tribunal permite rever as falas, examinar evidências, consultar o histórico e baixar um relatório Markdown. A demonstração funciona sem credenciais e mostra o fluxo com conteúdo editorial identificado.

O projeto roda no seu computador. Ele não oferece login ou hospedagem pública. O julgamento é automatizado: notas e classificações não garantem a verdade dos argumentos. A disponibilidade gratuita dos provedores também não garante que uma audiência termine.

## Executar

Requisitos: Python 3.11 ou superior, Node.js 22.18 ou superior e pnpm 11. A versão recomendada do Node permite executar também os testes que importam TypeScript diretamente. Os comandos abaixo partem da raiz do repositório clonado.

### Windows / PowerShell

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
if (!(Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
cd ..\frontend
pnpm install --frozen-lockfile
pnpm build
cd ..\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abra <http://127.0.0.1:8000>. O backend serve o frontend compilado. A demonstração pré-gravada não precisa de chaves e não consome APIs. Falas, notas e classificação da demonstração são conteúdo editorial ilustrativo, identificado na tela e no relatório.

Depois da instalação e do primeiro build, você pode iniciar pela raiz com:

```powershell
.\start.ps1
# Outra porta, se 8000 já estiver em uso:
.\start.ps1 -Port 8001
```

O script mantém o servidor em primeiro plano. Use `Ctrl+C` para encerrá-lo. Ele não instala dependências nem recompila o frontend. Para a porta alternativa, abra `http://127.0.0.1:8001`.

### macOS / Linux

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
[ -f .env ] || cp .env.example .env
cd ../frontend
pnpm install --frozen-lockfile
pnpm build
cd ../backend
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Desenvolvimento com atualização automática

Inicie o backend em um terminal, a partir de `backend`, com `.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload` no Windows. Em macOS/Linux, use `.venv/bin/python`.

Em outro terminal, a partir de `frontend`, execute `pnpm dev` e abra a URL informada pelo Vite. O proxy `/api` aponta para a porta 8000; CORS aceita as origens locais da porta 5173. Se alterar portas/origens de desenvolvimento, revise `vite.config.ts` e a configuração CORS em `main.py`. Reinícios por `--reload` interrompem partidas ativas; use o servidor sem reload para validar uma audiência completa.

Não sobrescreva um `.env` existente durante a instalação. Não use múltiplos workers Uvicorn: as tarefas da audiência são mantidas no processo.

## Configurar debates reais

Edite apenas `backend/.env`:

```dotenv
OPENROUTER_API_KEY=sua_chave
TAVILY_API_KEY=sua_chave
TAVILY_MONTHLY_BUDGET=1000
TRIBUNAL_DB=data/tribunal.sqlite3
```

| Variável | Uso e padrão |
| --- | --- |
| `OPENROUTER_API_KEY` | Chave privada para gerar falas/checagens/julgamento. Vazia: debates reais ficam indisponíveis. |
| `TAVILY_API_KEY` | Chave privada para pesquisar fatos. Vazia: pesquisa fica indisponível e fatos permanecem inconclusivos. |
| `TAVILY_MONTHLY_BUDGET` | Teto local de buscas por mês UTC; padrão 1.000, limitado pelo código ao intervalo de 0 a 1.000. Use um inteiro. Também limita o consumo de franquia da conta aceito pela integração. |
| `TRIBUNAL_DB` | Banco SQLite; padrão `data/tribunal.sqlite3`, relativo a `backend`. Um caminho absoluto também pode ser configurado. |

O `.env` é carregado na inicialização do módulo. Variáveis já exportadas no ambiente do processo têm prioridade. `/api/health` confirma apenas presença de configuração, não validade das chaves; `/api/limits` consulta a franquia OpenRouter. Não há chave de API no frontend.

- Crie uma chave no [OpenRouter](https://openrouter.ai/settings/keys). O catálogo ao vivo é filtrado por preços zero de entrada, saída e demais taxas declaradas. Modelos sem saída de texto são excluídos. O preço é revalidado antes de cada chamada. A aplicação envia tetos de preço zero, não habilita plugins pagos nem fallback de modelos. Registra o ID solicitado e o ID efetivamente retornado; o sufixo `:free` pode ser omitido pelo provedor na resposta.
- Crie uma chave no [Tavily](https://app.tavily.com), em conta Free sem cobrança por uso habilitada. O backend consulta `/usage` antes de cada nova pesquisa e bloqueia planos pagos, Pay As You Go habilitado, cota esgotada ou dados de faturamento indisponíveis. Busca basic custa um crédito; parâmetros automáticos estão desativados. Há reserva mensal local em SQLite e cache de 24 horas. A aplicação não altera o faturamento da conta. Prefira uma conta exclusiva gratuita: outros aplicativos podem consumir a mesma franquia.
- Reinicie o backend após alterar o `.env`. As chaves não vão para o navegador, transcrição ou Git. Não coloque segredos na pergunta.

Os limites e a disponibilidade gratuita variam. Consulte [limites do OpenRouter](https://openrouter.ai/docs/api_reference/limits), [preços do Tavily](https://www.tavily.com/pricing), [Tavily Usage](https://docs.tavily.com/documentation/api-reference/endpoint/usage) e [roteamento de provedores](https://openrouter.ai/docs/guides/routing/provider-selection).

## Como funciona

Para testar pela interface, abra a demonstração primeiro. Em um debate real, escreva uma pergunta de 8 a 2.000 caracteres, selecione os quatro modelos do catálogo atual e clique em **Iniciar audiência**. Os mesmos IDs podem ser usados para mais de um papel. Consulte a franquia antes de começar: uma pergunta inicia diversas chamadas.

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

Mapa resumido da estrutura (inventário completo em [ARQUIVOS.md](docs/ARQUIVOS.md)):

```text
backend/
  app/            API, grafo, schemas, integrações e persistência
    fixtures/     Demonstração editorial
  tests/          Testes sem serviços externos
frontend/
  src/            Interface, fila de leitura e estilos
  tests/          Testes da fila no Node
docs/             Inventário, arquitetura/API e prompts
.github/workflows/ Verificação contínua
start.ps1         Inicializador local do Windows
```

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

Confira [ARQUITETURA.md](docs/ARQUITETURA.md) para corpo de criação, respostas, estados, eventos SSE, tabelas do banco e limites de cada integração. O schema OpenAPI está disponível em <http://127.0.0.1:8000/openapi.json>.

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

Os testes do frontend validam ordem em rajadas, espera manual, pausa, velocidade, Unicode, modo automático, chegada de novos eventos, replay e avanço sem perda de etapa. `pnpm build` executa TypeScript e produz `dist`. Os dois grupos rodam automaticamente no [workflow de verificação](.github/workflows/checks.yml), sem credenciais.

Testes simulados não avaliam a qualidade dos argumentos de um modelo nem confirmam disponibilidade atual das APIs. Para validar uma integração real, use as chaves locais, consulte a franquia, acompanhe as fontes e exporte o relatório. Chamadas reais consomem requisições/créditos gratuitos; não fazem parte da suíte automatizada.

Se um modelo consumir a geração em raciocínio e retornar uma fala vazia, o backend aumenta o limite e tenta novamente, até três chamadas. Quando permitido pelo catálogo, o raciocínio opcional é desativado. O raciocínio interno nunca é usado como fala. Se o formato JSON estiver incorreto, a próxima tentativa recebe os erros de validação. Erros persistentes preservam o histórico e exibem uma mensagem específica.

Um erro 429 do OpenRouter pode indicar franquia diária esgotada ou limite de requisições/capacidade. O aplicativo identifica a franquia diária quando o provedor informa essa origem; nesse caso, trocar de modelo não resolve. No Tavily, `paygo_limit: null` é aceito somente quando o plano gratuito, o consumo e a franquia são confirmados e ainda existe um crédito inteiro dentro da franquia e do teto local de 1.000 créditos. O campo não é convertido em zero nem autoriza uso pago. Ausência de dados de consumo ou franquia, consumo pago, planos pagos e cota esgotada continuam bloqueando buscas. Falhas HTTP distinguem chave recusada (401), limite de requisições (429) e indisponibilidade da consulta de cota.

Na validação dessa integração, uma busca real retornou três fontes. Os testes também verificam que o tribunal preserva cada classificação do verificador: confirmada, contradita ou inconclusiva, com suas fontes. Falha de pesquisa continua produzindo inconclusão, sem evidência inventada.

## Diagnóstico de problemas

| Sintoma/código | O que significa e como agir |
| --- | --- |
| Backend offline | Confirme a porta e se Uvicorn está em execução. Consulte `/api/health`. |
| Página não aparece, mas `/docs` funciona | Faça `pnpm build` em `frontend` e reinicie o backend; o diretório estático é montado quando a aplicação é construída. |
| Alteração de tela não aparece | Em execução estática, recompile `dist` e recarregue a página. No desenvolvimento, use a URL do Vite. |
| Chave configurada, mas não funciona | Confirme o nome da variável no `.env`, reinicie o servidor e confira se uma variável exportada no processo está sobrepondo o arquivo. Não cole a chave em logs/issues. |
| `provider_daily_limit` / contador diário zero | A franquia de requisições gratuitas da conta acabou. Aguarde a renovação indicada e clique em Atualizar limites; trocar o modelo não renova a conta. |
| `provider_rate_limit` | Limite de requisições/capacidade não identificado como diário. Aguarde antes de repetir; outro modelo gratuito pode ter disponibilidade diferente. |
| `provider_quota` (402) | Provedor recusou a chamada por cota/créditos. Verifique limites da conta/chave; isso é diferente do contador diário 429. O aplicativo não habilita modelos pagos para contornar o erro. |
| `provider_limits_unavailable` | A consulta preventiva da franquia falhou. Confira chave, conectividade e disponibilidade do OpenRouter. |
| `provider_empty_output` | O modelo não produziu fala após três tentativas; raciocínio interno pode ter consumido a geração. O progresso permanece salvo. |
| `provider_invalid_json` | Respostas persistiram fora do schema mesmo com feedback. Confira os prompts, o contrato e as capacidades do modelo. |
| `provider_refusal` | Modelo recusou responder. Revise a pergunta antes de criar outra partida. |
| `search_auth_error` | Tavily recusou a chave (401). Revise `TAVILY_API_KEY` e reinicie. |
| `search_rate_limit` / `search_usage_unavailable` | Pesquisa ou consulta de franquia indisponível. O fato fica inconclusivo, sem fonte inventada. |
| `search_billing_unknown` / `search_paid_plan_blocked` | Não há dados suficientes para confirmar busca gratuita, ou há indicação de plano/cobrança paga. Revise a configuração da conta. `paygo_limit: null` isolado não bloqueia quando os demais dados confirmam a franquia. |
| `search_quota_exhausted` / orçamento mensal local esgotado | A busca não cabe na franquia gratuita ou no teto local. Aguarde renovação; não aumente o teto supondo que isso aumenta a franquia externa. |
| Todas as evidências inconclusivas | Leia as explicações/avisos. Pode haver falha de busca ou fontes insuficientes. Inconclusão não é contradição e nem sempre é erro técnico. |
| Servidor reiniciado | Partidas antigas em execução ficam interrompidas. Histórico/relatório continuam disponíveis; é necessário iniciar outra para executar novos argumentos. |
| Leitura pausada, mas a execução avançou | Esperado: os controles de reprodução afetam a tela. Para interromper chamadas, use Cancelar. |

Para relatar um problema, inclua ID da partida, estado, código/mensagem do aviso, etapa/rodada, IDs dos modelos e os passos para reproduzir. Confira `GET /api/matches/{id}` ou o relatório. Remova conteúdo privado antes de compartilhar. Nunca envie `.env`, cabeçalhos de autorização ou o banco inteiro.

### Dados locais e backup

O banco padrão fica em `backend/data/tribunal.sqlite3`; o Git ignora essa pasta. Pare o servidor antes de copiar o banco e eventuais arquivos `-wal`/`-shm`. Para testar com histórico separado, configure outro `TRIBUNAL_DB` e reinicie. Não há migrações ou limpeza automática. Preserve uma cópia antes de modificar armazenamento.

## Alterar o projeto

1. Crie uma branch a partir de `main` e consulte o [mapa de arquivos](docs/ARQUIVOS.md).
2. Para alterar argumentos/instruções, edite `SYSTEM` e as funções de `Tribunal` em `engine.py`; consulte a [lista completa de prompts](docs/PROMPTS.md). Campos da resposta ficam em `domain.py`, complemento JSON/tentativas em `providers.py`.
3. Para mudar leitura/balões, edite `playback.ts`, `main.tsx` e `style.css`. Preserve a separação entre evento completo e texto parcial.
4. Execute os testes relacionados e o build; atualize a documentação quando mudar contratos ou comportamento.
5. Faça commits que descrevam o resultado e abra um PR com motivo, escopo e validação. Não inclua segredos, dados locais, dependências instaladas ou build gerado.

Atualize os locks ao alterar dependências e confira a instalação com `--frozen-lockfile`. Não altere locks manualmente para esconder incompatibilidades. Novos arquivos versionados devem entrar no inventário. Mudanças no grafo devem manter testes de consenso, rejeição e limite de rodadas; mudanças de custo devem manter testes que bloqueiam caminhos pagos.

## Limitações da primeira versão

Execução local, um único processo Uvicorn, sem login, hospedagem, Supabase, RAG ou banco vetorial. Não execute múltiplos workers, pois as tarefas vivem no processo. Tentativas de inferência são limitadas a três para rede, 5xx e JSON inválido; cotas interrompem imediatamente. Pesquisas não repetem POST incerto, para não duplicar consumo. Erros de pesquisa produzem inconclusão, nunca fontes fictícias. A aplicação não garante a verdade de um julgamento de LLM.

Licença MIT. Cenário e sprites originais do projeto; ícones Lucide sob licença ISC.
