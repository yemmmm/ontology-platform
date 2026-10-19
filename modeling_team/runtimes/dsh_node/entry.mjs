// Explicit production composition: no CLI/profile discovery, user plugins or extra tools.
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { createInterface } from 'node:readline';
const config = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const load = async name => import(pathToFileURL(config.modules[name]).href);
const { Context } = await load('@deepseek-ai/cordis');
const ctx = new Context();
const mounted = [];
async function mount(name, options = {}) {
  const mod = await load(name);
  await ctx.plugin(mod.default ?? mod, options);
  mounted.push(name);
}
try {
  for (const name of ['llm', 'session', 'session-projection']) await mount(`@deepseek-ai/dsh-${name}`);
  await mount('@deepseek-ai/dsh-system-prompt', {
    personaPrefix: config.instructions, includeHarnessIdentity: false, includeRuntimeContext: false,
  });
  await mount('@deepseek-ai/dsh-tools', {mode: 'native'});
  await mount('@deepseek-ai/dsh-fs-local');
  await mount('@deepseek-ai/dsh-working-directory', {defaultDirectory: '/agent/work'});
  await mount('@deepseek-ai/dsh-agent');
  await mount('@deepseek-ai/dsh-session-persistence-jsonl', {root: '/agent/home/sessions', compression: 'none'});
  await mount('@deepseek-ai/dsh-session-checkpoint-policy');
  const providerOptions = {
    baseURL: config.providerURL, apiKeyEnv: 'DSH_PROXY_TOKEN', streamIdleTimeoutMs: 120000,
    ...(config.deliveryTools ? {reasoningEffort: config.reasoningEffort} : {}),
    // Unknown or partially streamed requests must await explicit Host recovery, never replay.
    retryPolicy: {mode: 'normal', maxRetries: 0},
  };
  if (config.provider === 'glm-messages') {
    // Reuse the pinned Messages codec without registering GLM as a DeepSeek provider.
    const {registerDeepSeekProvider, resolveAdapterOptions, catalogModelInfo} =
      await load('@deepseek-ai/dsh-llm-deepseek');
    const options = () => resolveAdapterOptions({...providerOptions,
      models: [{id: config.model}], maxTokens: 32768});
    await ctx.plugin({name: 'ontoweave-glm-messages', inject: ['llm'], apply(child) {
      registerDeepSeekProvider(child, 'glm-messages', {
        options, providerName: 'GLM Messages',
        resolveAuth: async () => ({headers: {'x-api-key': process.env.DSH_PROXY_TOKEN}}),
        discoverModels: async provider => options().models.map(model => catalogModelInfo(provider, model)),
      });
    }});
    mounted.push('ontoweave-glm-messages');
  } else {
    await mount('@deepseek-ai/dsh-llm-deepseek-api-key', providerOptions);
  }
  await mount('@deepseek-ai/dsh-agent-loop', {agents: []});
  await mount('@deepseek-ai/dsh-llm-retry');
  if (config.deliveryTools) await mount('@deepseek-ai/dsh-token-meter');
  await mount('@deepseek-ai/dsh-compaction-basic', config.deliveryTools ? {maxOverflowRetries: 0} : {});
  for (const server of config.servers) await mount('@deepseek-ai/dsh-mcp-client', {
    ...server, transport: 'stdio', command: '/usr/bin/python3', cwd: '/agent/work',
    toolCallTimeoutMs: 1200000, failOnStartupError: true,
    reconnect: {enabled: false},
  });
  // Use the SDK server directly so Host-only inspection stays outside model tools.
  if (config.deliveryTools) {
    const { serveDelivery } = await import('./delivery.mjs');
    await serveDelivery(ctx, config, mounted, load);
  } else {
  const { HarnessSdkJsonRpcServer } = await load('@deepseek-ai/dsh-sdk-jsonrpc-server');
  const send = value => process.stdout.write(JSON.stringify(value) + '\n');
  ctx.on('agent/error', ({agent, error}) => send({jsonrpc:'2.0', method:'host/provider-error',
    params:{sessionId:String(agent.id), code:error.code ?? 'agent-error',
      http_status:error.failure?.status ?? error.status ?? error.statusCode ?? null}}));
  const server = new HarnessSdkJsonRpcServer(ctx, {
    notify: (method, params) => send({jsonrpc:'2.0', method, params}),
    request: async () => { throw new Error('unexpected server request'); },
  }, {maxTokensAsSuccess: false});
  const inputs = createInterface({input: process.stdin});
  inputs.on('line', line => {
    // Request handlers run concurrently; notifications never wait for a prompt response.
    void (async () => {
      const request = JSON.parse(line);
      try {
        let result;
        if (request.method === 'host/inspect') {
          result = {plugins: mounted, tools: ctx.tools.schemas()};
        } else if (request.method === 'host/checkpoint') {
          const session = ctx.sessions.get(request.params.sessionId);
          if (!session) throw new Error('original session is unavailable');
          await ctx.sessions.flush(session);
          result = {};
        } else if (request.method === 'initialize') {
          result = await server.handleRequest(request.method, request.params);
          const effective = await ctx.llm.resolveCallConfig({provider: request.params.provider,
            model: request.params.model, reasoningEffort: request.params.reasoningEffort});
          result = {...result, effectiveBinding: effective};
        } else {
          result = await server.handleRequest(request.method, request.params ?? {});
        }
        send({jsonrpc:'2.0', id:request.id, result});
        if (request.method === 'shutdown') {
          await server.shutdown(); await ctx.fiber.dispose(); process.exit(0);
        }
      } catch (error) {
        send({jsonrpc:'2.0', id:request.id, error:{code:-32000, message:String(error.message)}});
      }
    })();
  });
  inputs.on('close', () => { void ctx.fiber.dispose().finally(() => process.exit(0)); });
  process.on('SIGTERM', () => { void ctx.fiber.dispose().finally(() => process.exit(0)); });
  }
} catch (error) {
  process.stderr.write(`DSH composition failed: ${error.message}\n`);
  await ctx.fiber.dispose();
  process.exit(1);
}
