# Guia de todos os arquivos

Este inventário cobre os arquivos versionados de código, configuração, testes e documentação. Os caminhos são relativos à raiz do repositório. Arquivos locais gerados e segredos aparecem ao final, sem seu conteúdo.

## Raiz e automação

| Arquivo | Responsabilidade e manutenção |
| --- | --- |
| [README.md](../README.md) | Entrada do projeto: instalação, configuração, uso, testes, problemas conhecidos e navegação pelos guias. Atualize quando mudar o comportamento público. |
| [LICENSE](../LICENSE) | Licença MIT do projeto. Preserve o texto legal e a atribuição ao redistribuir. |
| [.gitignore](../.gitignore) | Exclui credenciais, banco, caches, dependências, builds e trabalho temporário. A exceção `.env.example` permite versionar somente o modelo de configuração. |
| [start.ps1](../start.ps1) | Localiza o Python da `.venv`, exige `frontend/dist/index.html` e inicia Uvicorn em `127.0.0.1`, com porta configurável. Restaura o diretório ao sair. Não faz instalação/build. |
| [.github/workflows/checks.yml](../.github/workflows/checks.yml) | Executa testes Python e build/testes do frontend em push e PR. Usa Python 3.11, Node 22 e pnpm 11; não precisa de chaves de APIs. |

## Backend: configuração

| Arquivo | Responsabilidade e manutenção |
| --- | --- |
| [backend/.env.example](../backend/.env.example) | Nomes das chaves e padrões do orçamento e banco. Copie uma vez para `.env`; nunca inclua valores reais neste arquivo. |
| [backend/requirements.txt](../backend/requirements.txt) | Faixas das dependências diretas e ferramentas de teste. Serve como referência para atualização de dependências. |
| [backend/requirements.lock.txt](../backend/requirements.lock.txt) | Versões fixadas, incluindo dependências transitivas. É o arquivo instalado pelo README e pelo CI. Atualizações devem manter compatibilidade com as faixas e passar nos testes. |

## Backend: aplicação

| Arquivo | Contratos, dependências e pontos de atenção |
| --- | --- |
| [backend/app/__init__.py](../backend/app/__init__.py) | Identifica o pacote Python `app`. Não contém a configuração do servidor. |
| [backend/app/domain.py](../backend/app/domain.py) | Pydantic: `MatchRequest`, `Speech`, `Claim/Claims`, `Verification`, `Proposal`, `Acceptance`, `Confirmation`, `Score` e `Verdict`. Valida os quatro papéis, limites de texto e notas. `consensus_valid` exige aceitação do mesmo texto. Mudanças nos campos alteram os schemas dos prompts e podem afetar o frontend. |
| [backend/app/engine.py](../backend/app/engine.py) | `Tribunal` monta o `StateGraph`; `context` entrega falas/fontes sem identidade dos modelos; `ask` registra etapa, modelo real e fala. Nós de defesa, oposição, verificação, proposta, aceitação, confirmação e julgamento são sequenciais. `verify` valida IDs das fontes; `finish` calcula médias e contraditas. É o lugar para editar os prompts e as regras do debate. |
| [backend/app/providers.py](../backend/app/providers.py) | `OpenRouter` consulta catálogo/cotas, bloqueia preços não gratuitos, gera e valida JSON, e trata tentativas. `Tavily` consulta cota, reserva busca basic e usa cache. `ProviderError` e `SearchUnavailable` carregam mensagem, código e detalhes seguros. Não exponha respostas externas ou cabeçalhos de autorização em logs. |
| [backend/app/storage.py](../backend/app/storage.py) | `Store` cria tabelas e serializa JSON em SQLite; gera IDs e eventos sequenciais; mantém histórico, cache e orçamento. `BEGIN IMMEDIATE` protege sequência e reservas. `recover` interrompe partidas antigas no início do servidor. Alterações de schema precisam de estratégia de migração; não há migrações versionadas nesta versão. |
| [backend/app/main.py](../backend/app/main.py) | Carrega `.env`, constrói provedores/banco e expõe `create_app` para injeção nos testes. Mantém tarefas asyncio por partida; cuida de cancelamento e fechamento de clientes no lifespan. Expõe REST/SSE e serve `frontend/dist` se existir na construção da aplicação. `app` é o alvo do Uvicorn. Não use múltiplos workers. |
| [backend/app/demo.py](../backend/app/demo.py) | `fixture` lê o JSON editorial em UTF-8. `replay` publica eventos com atraso de 0,9 s por padrão e insere etapas antes das falas. A fila do frontend controla o tempo efetivo de leitura. Não usa provedores. |
| [backend/app/fixtures/demo.json](../backend/app/fixtures/demo.json) | Pergunta, falas, evidência e resultado ilustrativos de duas rodadas. Não é resultado de execução real das APIs. Ao editar, preserve tipos de evento, papéis, campos e a indicação editorial. |
| [backend/app/report.py](../backend/app/report.py) | `report(match, events)` retorna Markdown com pergunta, modo, modelos, falas, fontes, avisos e resultado disponível. Também funciona sem julgamento, em partidas canceladas/interrompidas. Não executa inferências nem pesquisas. |

## Backend: testes

| Arquivo | Cobertura |
| --- | --- |
| [backend/tests/test_tribunal.py](../backend/tests/test_tribunal.py) | LLM/busca simulados; consenso, rejeição, confirmação, cinco rodadas, cálculo de notas, três classificações, fontes, cota, cache, SSE, cancelamento, histórico, relatório e recuperação. |
| [backend/tests/test_provider_responses.py](../backend/tests/test_provider_responses.py) | `httpx.MockTransport` valida respostas vazias, raciocínio, JSON incorreto, recusas, tentativas, limites da conta e faturamento Tavily. `TestClient` verifica propagação de erro e bloqueio antes de criar uma partida. Não usa chaves reais. |

## Frontend

| Arquivo | Responsabilidade e manutenção |
| --- | --- |
| [frontend/index.html](../frontend/index.html) | Documento de entrada, idioma/metadados, nó `root` e carregamento do módulo React. |
| [frontend/package.json](../frontend/package.json) | Dependências React/Lucide/Vite/TypeScript e scripts `dev`, `build`, `preview`, `test`. O teste importa TypeScript diretamente no Node. |
| [frontend/pnpm-lock.yaml](../frontend/pnpm-lock.yaml) | Resolução fixa das dependências. Atualize pelo pnpm quando mudar dependências; use instalação com `--frozen-lockfile` para verificar reprodutibilidade. Não documente/edite manualmente cada entrada gerada. |
| [frontend/pnpm-workspace.yaml](../frontend/pnpm-workspace.yaml) | Autoriza o build de `esbuild`, necessário ao Vite no modelo de aprovação de scripts do pnpm. |
| [frontend/tsconfig.json](../frontend/tsconfig.json) | TypeScript estrito, JSX React, módulos para bundler, APIs DOM e `noEmit`. Abrange `src`; o Vite produz os arquivos finais. |
| [frontend/vite.config.ts](../frontend/vite.config.ts) | Plugin React e proxy `/api` para `127.0.0.1:8000` em desenvolvimento. Se mudar a porta do backend, ajuste o proxy; o frontend servido pelo FastAPI usa a mesma origem. |
| [frontend/src/main.tsx](../frontend/src/main.tsx) | Tipos de apresentação, sprites e componente `App`. Consulta configuração, catálogo e cotas; abre audiências; recebe snapshot/SSE e elimina duplicatas; mostra leitura, histórico, notas e fontes. `receivedEvents` é o histórico recebido, enquanto `Playback.visible` é o histórico já apresentado. Não deve conter chaves. |
| [frontend/src/playback.ts](../frontend/src/playback.ts) | Máquina de leitura independente de React/rede. `sync` recebe eventos; `tick(ms)` revela caracteres Unicode, respeita velocidade/pausa e espera entre falas; `next` completa/avança; `showAll` mostra o recebido; `reset` reinicia leitura preservando fonte, modo automático e velocidade. Fonte original não é alterada pela revelação parcial. |
| [frontend/src/style.css](../frontend/src/style.css) | Tokens visuais, cenário, sprites, mobiliário, balões ancorados, animações, formulários, evidências e resultado. Inclui breakpoints e redução de movimento. Verifique celular e desktop ao alterar posições/tamanhos. |
| [frontend/tests/playback.test.mjs](../frontend/tests/playback.test.mjs) | Testes Node da ordem em rajadas, espera manual, pausa, velocidade, Unicode, automático, chegada de novos eventos, replay e avanço sem perda da etapa. Usa `node:test` e `assert/strict`. |

## Documentação

| Arquivo | Conteúdo |
| --- | --- |
| [docs/ARQUIVOS.md](ARQUIVOS.md) | Este inventário completo e mapa de manutenção. Inclua aqui novos arquivos versionados. |
| [docs/ARQUITETURA.md](ARQUITETURA.md) | Fluxo de execução, estado, API, eventos SSE, tabelas e integrações. |
| [docs/PROMPTS.md](PROMPTS.md) | Todas as instruções do debate, composição das mensagens e contratos de resposta. O código continua sendo a fonte de verdade. |

## Arquivos locais não versionados

| Caminho | Uso |
| --- | --- |
| `backend/.env` | Credenciais privadas/configuração local. Reinicie o servidor após editar. Variáveis já exportadas no processo têm prioridade sobre `load_dotenv` padrão. |
| `backend/.venv/` | Ambiente Python local; recrie a partir do lock. |
| `backend/data/tribunal.sqlite3` | Banco padrão, com possíveis arquivos auxiliares `-wal` e `-shm`. Contém perguntas, falas e fontes reais; não publique esses dados. |
| `frontend/node_modules/` | Dependências instaladas pelo pnpm. |
| `frontend/dist/` | Bundle estático do build. Recompile após alterar o frontend. |
| `work/` | Diagnósticos e arquivos temporários locais. Não faz parte da entrega do código. |
| `__pycache__/`, `.pytest_cache/`, `*.tsbuildinfo`, `*.log` | Caches/saídas auxiliares. Não são fonte de implementação. |

Para fazer backup do banco, pare o servidor e copie o banco e seus auxiliares existentes. Para começar com um banco novo, prefira configurar outro `TRIBUNAL_DB`, preservando o histórico anterior.
