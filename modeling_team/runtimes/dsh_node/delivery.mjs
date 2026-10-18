// OntoWeave Host bridge, deliberately outside the model's tool registry.
export async function serveDelivery(ctx, config, mounted, load) {
  const { JsonRpcLineTransport } = await load('@deepseek-ai/dsh-sdk-protocol');
  const { HarnessSdkJsonRpcServer } = await load('@deepseek-ai/dsh-sdk-jsonrpc-server');
  const { createUserMessage } = await load('@deepseek-ai/dsh-llm');
  const transport = new JsonRpcLineTransport(process.stdin, process.stdout);
  const server = new HarnessSdkJsonRpcServer(ctx, transport, {maxTokensAsSuccess: false});
  const owned = id => {
    if (id !== config.sessionId) throw new Error('session outside Delivery ownership');
    const agent = ctx.agents.get(id);
    if (!agent) throw new Error('original Delivery session unavailable');
    return agent;
  };
  for (const tool of config.deliveryTools) ctx.tools.register({
    name: tool.name, description: tool.description, parameters: tool.inputSchema,
    output: {schema: {}, render: (_args, value) => [{type:'text', text:JSON.stringify(value)}]},
    execute: (args, exec) => {
      owned(String(exec.agent.id));
      return transport.request('ontoweave/delivery/tool', {
        sessionId:String(exec.agent.id), callId:exec.callId, name:tool.name, arguments:args,
      });
    },
  });
  ctx.on('agent/error', ({agent, error}) => transport.notify('host/provider-error', {
    sessionId:String(agent.id), code:error.code ?? 'agent-error',
    http_status:error.failure?.status ?? error.status ?? error.statusCode ?? null,
  }));
  let exiting;
  const exit = () => exiting ??= (async () => {
    await server.shutdown(); await transport.flush();
    await ctx.root.fiber.dispose(); transport.close(); process.exit(0);
  })();
  transport.onRequest(async (method, params) => {
    if (method === 'initialize') {
      await ctx.get('loader')?.await();
      const result = await server.handleRequest(method, params);
      return {...result, effectiveBinding:await ctx.llm.resolveCallConfig({
        provider:params.provider, model:params.model, reasoningEffort:params.reasoningEffort,
      })};
    }
    if (method === 'host/inspect') return {plugins:mounted, tools:ctx.tools.schemas()};
    if (method === 'ontoweave/delivery/steer') {
      const agent = owned(params.sessionId);
      const message = createUserMessage({content:[{type:'text', text:params.text}], source:{kind:'user'}});
      agent.steer(message);
      return {messageId:message.id};
    }
    if (method === 'ontoweave/delivery/interrupt') {
      owned(params.sessionId).cancel({kind:'user'}, {keepInbox:true});
      return {cancelSubmitted:true, keepInbox:true};
    }
    if (method === 'host/checkpoint') {
      owned(params.sessionId);
      await ctx.sessions.flush(ctx.sessions.get(params.sessionId));
      return {};
    }
    if (method === 'shutdown') { setImmediate(() => void exit()); return {}; }
    if (!['session/prompt', 'session/resume', 'session/wait'].includes(method))
      throw new Error('undeclared Delivery bridge method');
    if (params.sessionId !== config.sessionId) throw new Error('session outside Delivery ownership');
    return server.handleRequest(method, params);
  });
  process.stdin.on('end', () => void exit());
  process.on('SIGTERM', () => void exit());
  transport.start();
}
