// Numeric observation only. No arguments, result bodies, signals or identities are changed.
export function observeActivity(ctx, config, send = value => process.stdout.write(JSON.stringify(value) + '\n')) {
  const executed = new Set();
  const emit = (exec, event, status) => {
    try {
      send({jsonrpc:'2.0', method:'host/activity', params:{sessionId:String(exec.agent?.id ?? ''),
        event, call_id:String(exec.callId), root_call_id:String(exec.rootCallId ?? exec.callId),
        tool_name:exec.name, clock_ref:config.clockRef,
        // Decimal strings retain nanosecond precision across the JSON boundary.
        monotonic_ns:String(process.hrtime.bigint()), recorded_at:new Date().toISOString(), status}});
    } catch { /* An observer must never change execution or errors. */ }
  };
  const status = result => result?.error ? 'failed' : result?.isError ? 'failed' : 'completed';
  ctx.on('tools/execute', async (exec, next) => {
    executed.add(exec.callId);
    emit(exec, 'tool_start');
    let outcome = 'failed';
    try {
      const result = await next();
      outcome = status(result);
      return result;
    } finally {
      emit(exec, 'tool_end', exec.signal?.aborted ? 'cancelled' : outcome);
    }
  });
  ctx.on('tools/result', (exec, result) => {
    if (!executed.delete(exec.callId)) emit(exec, 'tool_rejected', exec.signal?.aborted ? 'cancelled' : 'rejected');
  });
}
