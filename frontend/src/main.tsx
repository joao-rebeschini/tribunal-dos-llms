import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Scale,
  Play,
  Square,
  History,
  Download,
  X,
  ArrowUpRight,
  ChevronRight,
  BookOpen,
  Check,
  Radio,
  RotateCcw,
  Sparkles,
  Shield,
  Swords,
  Search,
  Gavel,
  AlertCircle,
  Pause,
  SkipForward,
} from "lucide-react";
import "./style.css";
import { Playback } from "./playback";

type Role = "defesa" | "oposicao" | "verificador" | "juiz";
type Source = { id: number; title: string; url: string; content: string };
type Evidence = {
  round: number;
  role: Role;
  claim: string;
  status: string;
  explanation: string;
  sources: Source[];
};
type Score = {
  evidencias: number;
  coerencia: number;
  refutacoes: number;
  final: number;
  justification: string;
};
type Result = {
  conclusion: string;
  justification: string;
  consensus: boolean;
  rounds: number;
  divergences: string[];
  scores: Record<"defesa" | "oposicao", Score>;
  contradicted: Record<"defesa" | "oposicao", Evidence[]>;
};
type Speech = {
  role: Role;
  round: number;
  text: string;
  phase: string;
  accepted?: boolean;
};
type Event = {
  id: number;
  type: string;
  data: Speech &
    Evidence &
    Result & { message: string; demo: boolean; actual: string };
};
type Match = {
  id: string;
  question: string;
  status: string;
  demo: boolean;
  created_at: string;
  result: Result | null;
  events?: Event[];
};
const roles: Role[] = ["defesa", "oposicao", "verificador", "juiz"];
const labels: Record<Role, string> = {
  defesa: "Defesa",
  oposicao: "Oposição",
  verificador: "Verificador",
  juiz: "Juiz",
};
const icons = {
  defesa: Shield,
  oposicao: Swords,
  verificador: Search,
  juiz: Gavel,
};
const colors: Record<string, string> = {
  h: "#403333",
  s: "#d7a579",
  e: "#151b1d",
  w: "#e9e5d0",
  g: "#77ae8a",
  b: "#526e9d",
  r: "#a35b53",
  y: "#d3b36d",
  d: "#283237",
  t: "#b5bec1",
  p: "#766799",
};
const sprite = [
  ".....hhhhhh.....",
  "....hhhhhhhh....",
  "...hhhsssshhh...",
  "...hssssssssh...",
  "...hssesesssh...",
  "....ssssssss....",
  ".....ssssss.....",
  "......wwww......",
  "....ggwggwgg....",
  "...gggwggwggg...",
  "...sggggggggs...",
  "...sggggggggs...",
  "...ssggggggss...",
  ".....gggggg.....",
  ".....dddddd.....",
  ".....dd..dd.....",
  ".....dd..dd.....",
  "....eee..eee....",
];
function PixelPerson({
  role,
  active,
  phase,
}: {
  role: Role;
  active: boolean;
  phase: string;
}) {
  const outfit = { defesa: "g", oposicao: "r", verificador: "b", juiz: "d" }[
    role
  ];
  return (
    <div
      className={`person ${role} ${active ? "active" : ""} ${phase === "pesquisa" ? "researching" : phase === "julgamento" ? "judging" : "talking"}`}
      aria-hidden="true"
    >
      <div className="pixel-body">
        {sprite
          .join("")
          .split("")
          .map((c, i) => (
            <i
              key={i}
              style={{
                background:
                  c === "."
                    ? "transparent"
                    : colors[
                        c === "g"
                          ? outfit
                          : c === "h" && role === "juiz"
                            ? "t"
                            : c === "h" && role === "verificador"
                              ? "y"
                              : c
                      ],
              }}
            />
          ))}
      </div>
      {role === "juiz" && <div className="pixel-gavel" />}
      {role === "verificador" && <div className="pixel-book" />}
    </div>
  );
}

async function api<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch("/api" + url, options);
  if (!response.ok) {
    const body = await response
      .json()
      .catch(() => ({ detail: "Não foi possível acessar o servidor." }));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : "Confira a pergunta e a seleção dos quatro modelos.",
    );
  }
  return response.json();
}
function App() {
  const [question, setQuestion] = useState("");
  const [catalog, setCatalog] = useState<{ id: string; name: string }[]>([]);
  const [models, setModels] = useState<Record<string, string>>({});
  const [configured, setConfigured] = useState(false);
  const [match, setMatch] = useState<Match | null>(null);
  const [receivedEvents, setEvents] = useState<Event[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<Match[] | null>(null);
  const [tab, setTab] = useState("todas");
  const [replayKey, setReplayKey] = useState(0);
  const [, refreshPlayback] = useState(0);
  const playback = useRef(new Playback<Event>()).current;
  const bubbleText = useRef<HTMLDivElement>(null);
  const log = useRef<HTMLDivElement>(null);
  const allEvents = useRef<Event[]>([]);
  useEffect(() => {
    playback.reset();
    refreshPlayback(value => value + 1);
  }, [match?.id, replayKey, playback]);
  useEffect(() => {
    playback.sync(receivedEvents);
    refreshPlayback(value => value + 1);
  }, [receivedEvents, playback]);
  useEffect(() => {
    let previous = performance.now();
    const clock = setInterval(() => {
      const now = performance.now();
      const cursor = playback.cursor;
      const changed = playback.tick(Math.min(now - previous, 150));
      previous = now;
      if (changed || cursor !== playback.cursor) refreshPlayback(value => value + 1);
    }, 50);
    return () => clearInterval(clock);
  }, [playback]);
  const events = playback.visible;
  const presenting = playback.pending;
  useEffect(() => {
    api<{ openrouter_configured: boolean }>("/health")
      .then((x) => setConfigured(x.openrouter_configured))
      .catch(() =>
        setError(
          "O backend está offline. Inicie o servidor para abrir uma audiência.",
        ),
      );
    api<{ models: { id: string; name: string }[] }>("/models")
      .then((x) => {
        setCatalog(x.models);
        setModels(
          Object.fromEntries(
            roles.map((r, i) => [r, x.models[i % x.models.length]?.id || ""]),
          ),
        );
      })
      .catch(() =>
        setNotice(
          "Catálogo indisponível no momento. A demonstração continua disponível.",
        ),
      );
  }, []);
  useEffect(() => {
    if (!match?.id) return;
    let disposed = false;
    let stream: EventSource | undefined;
    const id = match.id;
    api<Match>("/matches/" + id)
      .then((snapshot) => {
        if (disposed) return;
        setMatch(snapshot);
        setEvents(snapshot.events || []);
        allEvents.current = snapshot.events || [];
        if (snapshot.status !== "running") return;
        stream = new EventSource(
          `/api/matches/${id}/events?after=${snapshot.events?.at(-1)?.id || 0}`,
        );
        stream.onopen = () => setNotice("");
        stream.onmessage = (e) => {
          const event: Event = JSON.parse(e.data);
          if (!allEvents.current.some(x => x.id === event.id)) allEvents.current = [...allEvents.current, event];
          setEvents((prev) =>
            prev.some((x) => x.id === event.id) ? prev : [...prev, event],
          );
          if (
            event.type === "result" ||
            event.type === "cancelled" ||
            event.type === "interrupted"
          ) {
            stream?.close();
            api<Match>("/matches/" + id).then((m) => {
              if (!disposed) {
                setMatch(m);
                allEvents.current = m.events || [];
              }
            });
          }
        };
        stream.onerror = () =>
          setNotice("Reconectando à audiência… O progresso está salvo.");
      })
      .catch((e) => setError(e.message));
    return () => {
      disposed = true;
      stream?.close();
    };
  }, [match?.id]);
  useEffect(() => {
    log.current?.scrollTo({
      top: log.current.scrollHeight,
      behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "instant"
        : "smooth",
    });
  }, [events]);
  useEffect(() => {
    if (bubbleText.current && playback.typing) bubbleText.current.scrollTop = bubbleText.current.scrollHeight;
  }, [events, playback]);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setHistory(null);
    };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, []);
  const speeches = events.filter((e) => e.type === "speech");
  const stage = events.filter((e) => e.type === "stage").at(-1)?.data;
  const last = speeches.at(-1)?.data;
  const evidence = events
    .filter((e) => e.type === "evidence")
    .map((e) => e.data);
  const result = events.find((e) => e.type === "result")?.data;
  const round = stage?.round || last?.round || 0;
  const live = match?.status === "running";
  const active = live || presenting ? stage?.role : undefined;
  const speaking = last && last.role === stage?.role && last.round === stage?.round && last.phase === stage?.phase;
  function control(action: () => void) {
    action();
    refreshPlayback(value => value + 1);
  }
  function bubble(role: Role) {
    if (active !== role) return null;
    return <div className={`speech-bubble bubble-${role}`}>
      <span>{labels[role]} <i>· Rodada {stage?.round}</i></span>
      <div className="bubble-text" ref={bubbleText}>
        <p>{speaking ? last.text : "Preparando a próxima intervenção…"}
          {speaking && playback.typing && <span className="typing-cursor" aria-hidden="true">▌</span>}
        </p>
      </div>
      <small>{speaking ? playback.typing ? "Texto progressivo · resposta validada" : "Fala completa · avance quando terminar de ler" : "Aguardando resposta"}</small>
    </div>;
  }
  const warnings = events.filter((e) =>
    ["warning", "interrupted", "cancelled"].includes(e.type),
  );
  async function start(demo = false) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const m = await api<Match>(demo ? "/demo" : "/matches", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        ...(demo
          ? {}
          : { body: JSON.stringify({ question: question.trim(), models }) }),
      });
      setReplayKey(value => value + 1);
      setEvents([]);
      setMatch(m);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function cancel() {
    if (!match) return;
    const m = await api<Match>(`/matches/${match.id}/cancel`, {
      method: "POST",
    }).catch((e) => {
      setError(e.message);
      return null;
    });
    if (m) setMatch(m);
  }
  function replayMatch() {
    const saved = allEvents.current;
    if (!saved.length) return;
    setEvents([...saved]);
    setReplayKey(value => value + 1);
  }
  async function openHistory() {
    try {
      setHistory(await api<Match[]>("/matches"));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const finished = match && !live;
  const tabs = ["todas", "confirmada", "contradita", "inconclusiva"];
  return (
    <div className="app">
      <aside className="rail">
        <a className="logo" href="#" aria-label="Tribunal dos LLMs">
          <Scale size={25} />
        </a>
        <div className="rail-line" />
        <button
          className="rail-button selected"
          onClick={() =>
            document
              .querySelector("#question")
              ?.scrollIntoView({ behavior: "smooth" })
          }
          title="Nova audiência"
          aria-label="Nova audiência"
        >
          <Gavel size={21} />
        </button>
        <button
          className="rail-button"
          onClick={openHistory}
          title="Histórico"
          aria-label="Abrir histórico"
        >
          <History size={21} />
        </button>
        <span className="rail-footer">
          T<br />L
        </span>
      </aside>
      <main>
        <header className="topbar">
          <div className="wordmark">
            TRIBUNAL <span>DOS LLMs</span>
          </div>
          <div className="top-actions">
            <span className="local">
              <i /> EXECUÇÃO LOCAL
            </span>
            <button className="text-button" onClick={openHistory}>
              <History size={15} /> Histórico
            </button>
          </div>
        </header>
        <section className="intro">
          <div>
            <div className="eyebrow">
              <span className="tiny-square" /> ARGUMENTOS EM JULGAMENTO
            </div>
            <h1>
              Uma pergunta.
              <br className="mobile-break" /> Quatro perspectivas.
            </h1>
            <p>
              A defesa argumenta. A oposição contesta. As fontes falam. O juiz
              decide.
            </p>
          </div>
          <button
            className="demo-button"
            onClick={() => start(true)}
            disabled={busy || live}
          >
            <Play size={16} fill="currentColor" /> Explorar demonstração{" "}
            <ArrowUpRight size={16} />
          </button>
        </section>
        {(error || notice) && (
          <div
            className={`notification ${error ? "error" : ""}`}
            role={error ? "alert" : "status"}
          >
            <AlertCircle size={16} />
            <span>{error || notice}</span>
            <button
              aria-label="Fechar aviso"
              onClick={() => {
                setError("");
                setNotice("");
              }}
            >
              <X size={16} />
            </button>
          </div>
        )}
        {match && (
          <div className="case-question">
            <span>EM PAUTA</span>
            <h2>{match.question}</h2>
          </div>
        )}
        <div className="arena-layout">
          <section className="court-panel">
            <div className="panel-bar">
              <div>
                <span className={`live-dot ${live || presenting ? "on" : ""}`} />
                {live
                  ? "AUDIÊNCIA EM ANDAMENTO"
                  : presenting
                    ? "REPRODUZINDO AUDIÊNCIA"
                    : finished
                      ? "AUDIÊNCIA ENCERRADA"
                      : "O TRIBUNAL ESTÁ PRONTO"}
              </div>
              <span>
                RODADA <strong>{round || "—"}</strong>
                <span className="muted"> / 5</span>
              </span>
            </div>
            <div
              className="court"
              aria-label="Tribunal em pixel art com quatro personagens"
            >
              <div className="wall-grid" />
              <div className="window left-window">
                <i />
                <i />
                <i />
                <i />
              </div>
              <div className="window right-window">
                <i />
                <i />
                <i />
                <i />
              </div>
              <div className="column col-left" />
              <div className="column col-right" />
              <div className="emblem">
                <Scale size={38} strokeWidth={1.5} />
              </div>
              <div className="wall-banner">
                <span>VERITAS</span>
              </div>
              <div className="court-floor" />
              <div
                className={`station judge-station ${active === "juiz" ? "lit" : ""}`}
              >
                <PixelPerson
                  role="juiz"
                  active={active === "juiz"}
                  phase={stage?.phase || ""}
                />
                {bubble("juiz")}
                <div className="judge-desk">
                  <div className="desk-detail" />
                  <span>JUIZ</span>
                </div>
              </div>
              <div
                className={`station defense-station ${active === "defesa" ? "lit" : ""}`}
              >
                <PixelPerson
                  role="defesa"
                  active={active === "defesa"}
                  phase={stage?.phase || ""}
                />
                {bubble("defesa")}
                <div className="podium">
                  <span>DEFESA</span>
                  <i />
                </div>
              </div>
              <div
                className={`station opposition-station ${active === "oposicao" ? "lit" : ""}`}
              >
                <PixelPerson
                  role="oposicao"
                  active={active === "oposicao"}
                  phase={stage?.phase || ""}
                />
                {bubble("oposicao")}
                <div className="podium">
                  <span>OPOSIÇÃO</span>
                  <i />
                </div>
              </div>
              <div
                className={`station verifier-station ${active === "verificador" ? "lit" : ""}`}
              >
                <PixelPerson
                  role="verificador"
                  active={active === "verificador"}
                  phase={stage?.phase || ""}
                />
                {bubble("verificador")}
                <div className="research-desk">
                  <span>VERIFICADOR</span>
                  <div className="books">
                    <i />
                    <i />
                    <i />
                  </div>
                </div>
              </div>
              <div className="court-foreground" />
              <div className="torch torch-left">
                <i />
              </div>
              <div className="torch torch-right">
                <i />
              </div>
              {!match && (
                <div className="idle-note">
                  <span>QUANDO A DÚVIDA ENTRA,<br />O DEBATE COMEÇA.</span>
                  <small>Escreva uma pergunta ou explore a demonstração.</small>
                </div>
              )}
              {match?.demo && (
                <div className="demo-tag">
                  <Play size={10} /> DEMONSTRAÇÃO PRÉ-GRAVADA
                </div>
              )}
            </div>
            {match && <div className="playback-controls">
              <div className="playback-heading">
                <strong>{playback.paused ? "Leitura pausada" : playback.waiting ? "Sua vez de avançar" : playback.typing ? "Argumento em apresentação" : presenting ? "Próxima intervenção" : live ? "Aguardando os agentes" : "Reprodução concluída"}</strong>
                <span>{live ? "Os agentes continuam trabalhando." : match.status === "interrupted" ? "Processamento interrompido · acompanhe as falas recebidas." : "Debate processado · leia no seu ritmo."}</span>
              </div>
              <div className="playback-actions">
                <button onClick={() => control(() => { playback.paused = !playback.paused; })} disabled={!presenting}>
                  {playback.paused ? <Play size={14} /> : <Pause size={14} />}{playback.paused ? "Continuar" : "Pausar"}
                </button>
                <button className="advance-button" onClick={() => control(() => playback.next())} disabled={!presenting}>
                  <ChevronRight size={15} />{playback.typing ? "Mostrar fala completa" : "Próxima fala"}
                </button>
                <label><input type="checkbox" checked={playback.automatic} onChange={e => control(() => { playback.automatic = e.target.checked; })} /> Automático</label>
                <label>Velocidade <select aria-label="Velocidade do texto" value={playback.speed} onChange={e => control(() => { playback.speed = Number(e.target.value); })}>
                  <option value="0.5">0,5×</option><option value="1">1×</option><option value="2">2×</option>
                </select></label>
                <button onClick={() => control(() => playback.showAll())} disabled={!presenting}><SkipForward size={14} /> Ver tudo</button>
              </div>
              <small>Uma fala de cada vez. O texto aparece após a validação da resposta; pausa e velocidade controlam apenas a leitura.</small>
            </div>}
            <div className="court-footer">
              <span>
                <Radio size={13} />{" "}
                {match?.demo
                  ? "Conteúdo ilustrativo · sem consumo de APIs"
                  : "Quatro agentes · até cinco rodadas"}
              </span>
              <div>
                {live && (
                  <button className="text-button danger" onClick={cancel}>
                    <Square size={12} /> Cancelar
                  </button>
                )}
                {finished && (
                  <>
                    <button
                      className="text-button"
                      onClick={replayMatch}
                      disabled={presenting}
                    >
                      <RotateCcw size={13} /> Rever
                    </button>
                    <a
                      className="text-button"
                      href={`/api/matches/${match.id}/report`}
                      download
                    >
                      <Download size={13} /> Relatório
                    </a>
                  </>
                )}
              </div>
            </div>
          </section>
          <section className="transcript panel">
            <div className="section-title">
              <div>
                <BookOpen size={16} />
                <h2>Registro da audiência</h2>
              </div>
              <span className="count">{speeches.length}</span>
            </div>
            <div
              className="transcript-scroll"
              ref={log}
              aria-label="Transcrição das falas apresentadas"
            >
              {!speeches.length ? (
                <div className="empty-log">
                  <div className="empty-icon">
                    <BookOpen size={28} />
                  </div>
                  <h3>
                    Todos os argumentos,
                    <br />
                    no mesmo lugar.
                  </h3>
                  <p>
                    As falas dos participantes aparecerão aqui, rodada por
                    rodada.
                  </p>
                  <div className="role-legend">
                    {roles.map((r) => {
                      const Icon = icons[r];
                      return (
                        <span className={r} key={r}>
                          <Icon size={13} />
                          {labels[r]}
                        </span>
                      );
                    })}
                  </div>
                </div>
              ) : (
                speeches.map((e) => {
                  const d = e.data;
                  const Icon = icons[d.role];
                  return (
                    <article className={`log-entry ${d.role}`} key={e.id}>
                      <div className="log-heading">
                        <span>
                          <Icon size={13} />
                          {labels[d.role]}
                        </span>
                        <small>
                          R{d.round} · {d.phase}
                        </small>
                      </div>
                      <p>{d.text}</p>
                      {d.phase === "aceitacao" && (
                        <span
                          className={`accept-tag ${d.accepted ? "yes" : "no"}`}
                        >
                          {d.accepted
                            ? "Proposta aceita"
                            : "Proposta rejeitada"}
                        </span>
                      )}
                    </article>
                  );
                })
              )}
            </div>
          </section>
        </div>
        {warnings.length > 0 && (
          <div className="warning-box" role="status">
            <AlertCircle size={16} />
            <p>{warnings.at(-1)?.data.message}</p>
          </div>
        )}
        {result && (
          <section className="verdict panel">
            <div className="verdict-heading">
              <span className="verdict-icon">
                <Gavel size={25} />
              </span>
              <div>
                <div className="eyebrow">
                  {match?.demo
                    ? "JULGAMENTO ILUSTRATIVO"
                    : "JULGAMENTO AUTOMATIZADO"}
                </div>
                <h2>
                  {result.consensus
                    ? "O tribunal chegou a um consenso."
                    : "O tribunal decidiu, com divergências."}
                </h2>
              </div>
              <span className="result-round">{result.rounds} rodadas</span>
            </div>
            <p className="conclusion">{result.conclusion}</p>
            <p className="result-reason">{result.justification}</p>
            <div className="scores">
              {(["defesa", "oposicao"] as const).map((r) => (
                <div className={`score ${r}`} key={r}>
                  <span>{labels[r]}</span>
                  <strong>
                    {result.scores[r].final.toLocaleString("pt-BR")}
                    <small> / 10</small>
                  </strong>
                  <div className="score-details">
                    {(["evidencias", "coerencia", "refutacoes"] as const).map(
                      (key, i) => (
                        <span key={key}>
                          {["Evidências", "Coerência", "Refutações"][i]}{" "}
                          <b>{result.scores[r][key]}</b>
                        </span>
                      ),
                    )}
                  </div>
                  <p>{result.scores[r].justification}</p>
                  <small>
                    Afirmações contraditas:{" "}
                    <b>{result.contradicted[r].length}</b>
                  </small>
                  {result.contradicted[r].map((c, i) => (
                    <p key={i}>
                      {c.claim} — {c.explanation}
                    </p>
                  ))}
                </div>
              ))}
            </div>
            {result.divergences.length > 0 && (
              <div className="divergences">
                <h3>Divergências preservadas</h3>
                {result.divergences.map((d, i) => (
                  <p key={i}>{d}</p>
                ))}
              </div>
            )}
            <small className="scoring-note">
              Nota final: média simples de evidências, coerência e refutações.
              Ausência de fontes não conta como alucinação.
            </small>
          </section>
        )}
        <div className="bottom-layout">
          <section className="setup panel">
            <div className="section-title">
              <div>
                <Sparkles size={16} />
                <h2>Abra uma audiência</h2>
              </div>
              <span className="step-label">01 / PERGUNTA</span>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void start();
              }}
            >
              <label htmlFor="question">
                O que você quer colocar em debate?
              </label>
              <textarea
                id="question"
                placeholder="Ex.: A inteligência artificial deve substituir professores?"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                minLength={8}
                maxLength={2000}
                required
                disabled={live}
              />
              <div className="examples">
                <span>EXPERIMENTE</span>
                {["IA na educação", "Semana de 4 dias", "Energia nuclear"].map(
                  (text, i) => (
                    <button
                      type="button"
                      key={text}
                      disabled={live}
                      onClick={() =>
                        setQuestion(
                          [
                            "A inteligência artificial deve substituir professores?",
                            "A semana de trabalho de quatro dias deve ser adotada?",
                            "A energia nuclear deve fazer parte da transição energética?",
                          ][i],
                        )
                      }
                    >
                      {text}
                      <ChevronRight size={11} />
                    </button>
                  ),
                )}
              </div>
              <div className="models-heading">
                <span>02 / ESCOLHA OS MODELOS</span>
                <span className="free-label">
                  <Check size={11} /> Somente gratuitos
                </span>
              </div>
              <div className="model-grid">
                {roles.map((r) => {
                  const Icon = icons[r];
                  return (
                    <label className={`model-select ${r}`} key={r}>
                      <span>
                        <Icon size={13} />
                        {labels[r]}
                      </span>
                      <select
                        value={models[r] || ""}
                        onChange={(e) =>
                          setModels({ ...models, [r]: e.target.value })
                        }
                        disabled={live || !catalog.length}
                        aria-label={`Modelo da ${labels[r]}`}
                      >
                        <option value="" disabled>
                          {catalog.length
                            ? "Selecione um modelo"
                            : "Catálogo indisponível"}
                        </option>
                        {catalog.map((m) => (
                          <option key={m.id} value={m.id}>
                            {m.name}
                          </option>
                        ))}
                      </select>
                    </label>
                  );
                })}
              </div>
              <button
                className="start-button"
                disabled={
                  busy || live || !configured || roles.some((r) => !models[r])
                }
              >
                <Play size={15} fill="currentColor" />
                {busy ? "Preparando audiência…" : "Iniciar audiência"}
                <span>ATÉ 5 RODADAS</span>
              </button>
              {!configured && (
                <p className="config-note">
                  Configure as chaves no backend para debates reais. A
                  demonstração está pronta para explorar.
                </p>
              )}
            </form>
          </section>
          <section className="evidence-panel panel">
            <div className="section-title">
              <div>
                <Search size={16} />
                <h2>Mesa de evidências</h2>
              </div>
              <span className="count">{evidence.length}</span>
            </div>
            <div
              className="evidence-tabs"
              role="group"
              aria-label="Filtrar evidências"
            >
              {tabs.map((t, i) => (
                <button
                  className={tab === t ? "selected" : ""}
                  key={t}
                  onClick={() => setTab(t)}
                  aria-pressed={tab === t}
                >
                  {["Todas", "Confirmadas", "Contraditas", "Inconclusivas"][i]}
                  <span>
                    {t === "todas"
                      ? evidence.length
                      : evidence.filter((e) => e.status === t).length}
                  </span>
                </button>
              ))}
            </div>
            <div className="evidence-content">
              {!evidence.length ? (
                <div className="evidence-empty">
                  <div className="paper-stack">
                    <Search size={27} />
                  </div>
                  <h3>Uma boa conclusão precisa de boas fontes.</h3>
                  <p>
                    O verificador pesquisa até três afirmações por rodada.
                    <br />
                    Cada fonte fica ligada ao argumento que ela verifica.
                  </p>
                  <span>
                    <i /> Fatos, opiniões e incertezas têm lugares diferentes.
                  </span>
                </div>
              ) : evidence.filter((e) => tab === "todas" || e.status === tab)
                  .length === 0 ? (
                <p className="filter-empty">
                  Nenhuma afirmação nesta classificação.
                </p>
              ) : (
                evidence
                  .filter((e) => tab === "todas" || e.status === tab)
                  .map((e, i) => (
                    <article className="evidence-card" key={i}>
                      <div>
                        <span className={`status-tag ${e.status}`}>
                          {e.status}
                        </span>
                        <small>
                          R{e.round} · {labels[e.role]}
                        </small>
                      </div>
                      <h3>{e.claim}</h3>
                      <p>{e.explanation}</p>
                      {e.sources.map((s) => (
                        <a
                          key={s.id}
                          href={s.url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          <BookOpen size={12} />
                          {s.title}
                          <ArrowUpRight size={12} />
                        </a>
                      ))}
                    </article>
                  ))
              )}
            </div>
            <div className="evidence-footer">
              <Shield size={12} /> A avaliação das fontes também é automatizada.
            </div>
          </section>
        </div>
        <footer className="page-footer">
          <span>FEITO PARA QUESTIONAR. PROJETADO PARA ARGUMENTAR.</span>
          <span>
            FastAPI + LangGraph + React <i>·</i> v1.0
          </span>
        </footer>
      </main>
      {history && (
        <div className="modal-backdrop" onClick={() => setHistory(null)}>
          <section
            className="history-modal panel"
            role="dialog"
            aria-modal="true"
            aria-label="Histórico de audiências"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="section-title">
              <div>
                <History size={18} />
                <h2>Histórico de audiências</h2>
              </div>
              <button
                autoFocus
                className="text-button"
                onClick={() => setHistory(null)}
                aria-label="Fechar histórico"
              >
                <X size={19} />
              </button>
            </div>
            {!history.length && (
              <p className="filter-empty">Suas audiências aparecerão aqui.</p>
            )}
            <div className="history-list">
              {history.map((m) => (
                <button
                  key={m.id}
                  onClick={async () => {
                    setReplayKey(value => value + 1);
                    setHistory(null);
                    try {
                      const snapshot = await api<Match>("/matches/" + m.id);
                      setMatch(snapshot);
                      setEvents(snapshot.events || []);
                      allEvents.current = snapshot.events || [];
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  <div>
                    <span>
                      {m.demo ? "DEMONSTRAÇÃO" : "DEBATE REAL"} ·{" "}
                      {new Date(m.created_at).toLocaleString("pt-BR")}
                    </span>
                    <strong>{m.question}</strong>
                    <small>
                      {
                        (
                          {
                            running: "Em andamento",
                            completed: "Concluída",
                            cancelled: "Cancelada",
                            interrupted: "Interrompida",
                          } as Record<string, string>
                        )[m.status]
                      }
                    </small>
                  </div>
                  <ChevronRight size={18} />
                </button>
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
