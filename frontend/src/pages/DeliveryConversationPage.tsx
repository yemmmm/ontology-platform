import { useEffect, useRef, useState } from "react";
import { useT } from "../i18n";
import { workspaceApi } from "../workspaceApi";
import type { Project, ConversationIndex, ConversationStatus, ConversationMessage, ConversationInput, ConversationEvent } from "../workspaceTypes";

const controls = [
  ["pause", "Pause flow"], ["resume", "Continue flow"], ["cancel", "Cancel work"],
  ["revoke_budget", "Revoke budget"], ["stop", "Stop Team"],
] as const;

function basisText(value: unknown) {
  if (typeof value === "string") return value;
  if (value && typeof value === "object") {
    const basis = value as { evidence_references?: string[]; limitations?: string };
    return [...(basis.evidence_references ?? []), basis.limitations].filter(Boolean).join(" · ");
  }
  return "";
}

export function DeliveryConversationPage({ project }: { project: Project }) {
  const t = useT();
  const [index, setIndex] = useState<ConversationIndex>();
  const [selection, setSelection] = useState("");
  const [status, setStatus] = useState<ConversationStatus>();
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [question, setQuestion] = useState("");
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const [pending, setPending] = useState<ConversationInput>();
  const [hasMore, setHasMore] = useState(false);
  const cursor = useRef(0);
  const epoch = useRef(0);
  const polling = useRef(false);
  const selected = useRef(selection);
  selected.current = selection;

  useEffect(() => {
    let active = true;
    workspaceApi.conversations(project.id).then(data => {
      if (!active) return;
      setIndex(data);
      let remembered = "";
      try { remembered = localStorage.getItem(`delivery-conversation:${project.id}`) ?? ""; } catch { /* Optional preference. */ }
      setSelection(data.items.some(x => x.delivery_session_id === remembered) ? remembered : "");
    }).catch(reason => { if (active) setError(String(reason)); });
    return () => { active = false; epoch.current++; };
  }, [project.id]);

  function apply(events: ConversationEvent[]) {
    setMessages(previous => {
      const all = new Map(previous.map(m => [m.message_id, m]));
      for (const event of events) {
        const identity = event.message_id;
        if (identity && event.message && ["message_received", "delivery_message"].includes(event.event_type)) {
          all.set(identity, { ...event.message, message_id: identity, recorded_at: event.recorded_at,
            received_seq: event.event_seq, dispatch: event.event_type === "delivery_message" ? "published" : "pending" });
        } else if (identity && all.has(identity)) {
          const prior = all.get(identity)!;
          if (event.event_type === "dispatch_started") all.set(identity, { ...prior, dispatch: "unknown" });
          if (event.event_type === "dispatch_result") all.set(identity, { ...prior, dispatch: event.status });
          if (event.event_type === "control_result") all.set(identity, { ...prior, control: { action: event.action ?? "", status: event.status ?? "unknown", basis: event.basis } });
        }
      }
      return [...all.values()].sort((a, b) => (a.received_seq ?? 0) - (b.received_seq ?? 0));
    });
  }

  async function refresh(session = selection, version = epoch.current) {
    if (!session || polling.current) return;
    polling.current = true;
    try {
      const [state, page] = await Promise.all([
        workspaceApi.conversation(project.id, session),
        workspaceApi.conversationEvents(project.id, session, cursor.current),
      ]);
      if (version !== epoch.current || session !== selected.current) return;
      setStatus(state); apply(page.items); cursor.current = page.next_after_seq; setHasMore(page.has_more);
      if (!page.history_complete) setError(t("Conversation history is incomplete"));
    } catch (reason) { if (version === epoch.current) setError(String(reason)); }
    finally { polling.current = false; }
  }

  useEffect(() => {
    const version = ++epoch.current;
    cursor.current = 0; setMessages([]); setStatus(undefined); setQuestion(""); setPending(undefined); setError(""); setSending(false); setDraft("");
    if (!selection) return;
    try { localStorage.setItem(`delivery-conversation:${project.id}`, selection); } catch { /* Optional preference. */ }
    void refresh(selection, version);
    const tick = () => { if (!document.hidden) void refresh(selection, version); };
    const timer = window.setInterval(tick, 2000);
    document.addEventListener("visibilitychange", tick);
    return () => { clearInterval(timer); document.removeEventListener("visibilitychange", tick); epoch.current++; };
  }, [selection, project.id]);

  async function send(input: ConversationInput) {
    const version = epoch.current, session = selection;
    setSending(true); setError("");
    try {
      const result = await workspaceApi.conversationSend(project.id, session, input);
      if (version !== epoch.current) return;
      setPending(undefined);
      if (input.kind !== "control") { setDraft(""); setQuestion(""); }
      setMessages(prior => [...prior.filter(m => m.message_id !== result.message.message_id), result.message].sort((a, b) => (a.received_seq ?? 0) - (b.received_seq ?? 0)));
      await refresh(session, version);
    } catch (reason) {
      if (version !== epoch.current) return;
      if (String(reason).includes("422 ")) { setError(String(reason)); setPending(undefined); return; }
      setPending(input); setError(String(reason));
      // Check the original identity first. A timeout does not prove non-acceptance.
      try {
        const receipt = await workspaceApi.conversationReceipt(project.id, session, input.message_id);
        if (version !== epoch.current) return;
        setPending(undefined);
        if (input.kind !== "control") setDraft("");
        setMessages(prior => [...prior.filter(m => m.message_id !== receipt.message_id), receipt]);
        await refresh(session, version);
      } catch { /* Keep the original envelope for an explicit retry; never change its ID. */ }
    } finally { if (version === epoch.current) setSending(false); }
  }

  const online = status?.connection === "online" && !["stopping", "stopped"].includes(status.activity);
  function sendDraft() {
    if (!online || !draft.trim() || sending || pending) return;
    void send({ message_id: crypto.randomUUID(), kind: question ? "answer" : "message", text: draft,
      ...(question ? { reply_to_message_id: question } : {}) });
  }

  return <section className="conversationPage">
    <div className="pageHeading"><p>{project.name}</p></div>
    <section className="panel">
      <label>{t("Delivery conversation")}<select aria-label={t("Delivery conversation")} value={selection} onChange={event => setSelection(event.target.value)}>
        <option value="">{t("Select a conversation")}</option>
        {index?.items.map(item => <option key={item.delivery_session_id} value={item.delivery_session_id}>{item.delivery_session_id}</option>)}
      </select></label>
      {index && !index.items.length && <p>{t("No Delivery conversations")}</p>}
      {index && !index.enumeration_complete && <p className="warningMessage">{t("Conversation enumeration is incomplete")}</p>}
    </section>
    {error && <p className="errorMessage" role="alert">{error}</p>}
    {selection && <>
      <section className="panel conversationStatus" aria-label={t("Conversation status")}>
        <p>{t("Connection")}: {t(status?.connection ?? "unknown")} · {t("Flow state")}: {t(status?.activity ?? "unknown")}</p>
        <p>{t("Observed")}: {status?.observed_at ?? t("Unknown")}</p>
        <p>{t("Status basis")}: {basisText(status?.basis) || t("Unknown")}</p>
        <p>{t("History starts")}: {status?.history_started_at ?? t("Unknown")} — {t("Earlier records are not included")}</p>
        {status?.delivery_result && <p>{status.delivery_result}</p>}
        {!online && <p>{t("Resume through the original Host entry before sending")}</p>}
        <button type="button" onClick={() => void refresh()}>{t("Refresh")}</button>
      </section>
      <div className="conversationLayout">
        <section className="panel conversationTimeline" aria-label={t("Conversation history")}>
          {!messages.length && <p>{t("No new messages")}</p>}
          {messages.map(item => <article className={`conversationMessage ${item.sender?.kind === "delivery" ? "fromDelivery" : ""}`} key={item.message_id}>
            <div className="conversationMessageMeta">{t(item.sender?.kind ?? "unknown")} {item.sender?.reference} · {t(item.entrypoint ?? "unknown")} · <time>{item.recorded_at}</time></div>
            {item.submitted_by && (item.submitted_by.kind !== item.sender?.kind || item.submitted_by.reference !== item.sender?.reference) && <small>{t("Forwarded by")}: {t(item.submitted_by.kind)} {item.submitted_by.reference}</small>}
            <p className="conversationText">{item.text}</p>
            {item.reply_to_message_id && <small>{t("Reply to")}: {messages.find(m => m.message_id === item.reply_to_message_id)?.text ?? item.reply_to_message_id}</small>}
            <p className="conversationMessageMeta">{t(item.dispatch ?? "unknown")}{item.control ? ` · ${t(item.control.status)}` : ""}</p>
            {item.control?.basis != null && <p className="conversationMessageMeta">{t("Control basis and limits")}: {basisText(item.control.basis)}</p>}
          </article>)}
          {hasMore && <button onClick={() => void refresh()}>{t("Load more messages")}</button>}
        </section>
        <aside className="panel conversationComposer">
          <label>{t("Answer a question")}<select aria-label={t("Answer a question")} value={question} onChange={event => setQuestion(event.target.value)}>
            <option value="">{t("Proactive message")}</option>
            {status?.pending_questions.map(item => <option key={item.message_id} value={item.message_id}>{item.text}</option>)}
          </select></label>
          <label>{t("Message")}<textarea aria-label={t("Message")} rows={7} value={draft} onChange={event => setDraft(event.target.value)}
            onKeyDown={event => { if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) { event.preventDefault(); sendDraft(); } }} /></label>
          <button disabled={!online || !draft.trim() || sending || !!pending} onClick={sendDraft}>{t("Send message")}</button>
          {pending && <button disabled={sending || !online} onClick={() => void send(pending)}>{t("Retry original message")}</button>}
          <p>{t("Received and delivered do not mean business work is complete")}</p>
          <div className="conversationControls">{controls.map(([action, label]) => <button key={action} disabled={!online || sending || !!pending} onClick={() => void send({ message_id: crypto.randomUUID(), kind: "control", action, text: t(label) })}>{t(label)}</button>)}</div>
        </aside>
      </div>
    </>}
  </section>;
}
