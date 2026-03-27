# DECISION LOG

Registro de decisoes de arquitetura, design e protocolo. Cada entrada documenta
o que foi decidido, por que, e quais alternativas foram descartadas.

---

## [DEC-026] 2026-03-27 - Protocolo E Agora: Claude API para gestao de posicao em baixa

Decisao: criar protocolo de gestao de risco acionado manualmente via Telegram
que busca todos os dados da posicao aberta e chama a Claude API para propor
exatamente 2 cenarios situacionais.

Racional: o operador ja geria posicoes perdedoras no olho com eficiencia, mas
sem protocolo — decisoes inconsistentes dependendo do estado emocional do
momento. Formalizar em 2 cenarios forcados elimina o viés de inacao (ficar
segurando sem plano) e o de pânico (fechar tudo sem avaliacao). O modelo recebe
dados reais de mercado (BB levels, MACD, StochRSI) e escolhe os 2 cenarios mais
relevantes do leque — nao uma lista fixa — o que torna a resposta situacional em
vez de generica.

O prompt e em ingles para qualidade de raciocinio do modelo. O output e
instrucido em portugues para uso direto no chat.

Alternativas descartadas: lista fixa de cenarios pre-calculados sem IA.
Descartada porque ignora o contexto especifico do mercado no momento — o mesmo
ativo com o mesmo PnL pode ter tratamentos completamente diferentes dependendo
de onde esta o preco em relacao as Bollinger Bands. Resposta puramente
deterministica sem Claude API. Descartada por incapacidade de ponderar multiplos
fatores simultaneamente e escolher os 2 cenarios mais relevantes.

---

## [DEC-027] 2026-03-27 - Janela de 60 minutos para classificacao rescue no analyzer

Decisao: trades fechados ou abertos em ate 60 minutos apos um pedido E agora
para o mesmo simbolo sao classificados na categoria rescue, com prioridade
abaixo de claudinho_confirm e claudinho_loop.

Racional: o rescue nao e um sinal de entrada imediata — e uma analise de
situacao. O operador pode levar alguns minutos para avaliar os cenarios, decidir
e executar. Uma janela curta (5 ou 10 minutos) perderia a maioria dos trades
influenciados pelo protocolo. 60 minutos cobre o horizonte realista de acao pos-
consulta sem contaminar trades completamente independentes. Rescue e subconjunto
conceitualmente distinto de olho: o operador consultou o agente antes de agir,
mesmo que nao tenha seguido o conselho à risca.

Alternativas descartadas: janela de 10 minutos, igual ao claudinho_loop.
Descartada porque o rescue envolve leitura, avaliacao e execucao deliberada —
nao entrada reflexa. Janela de 120 minutos. Descartada por contaminar trades
subsequentes sem relacao com o pedido original.

---

## [DEC-023] 2026-03-26 - Classificacao de trades em quatro categorias

Decisao: expandir a classificacao de trades de binaria (claudinho/olho) para
quatro categorias com prioridade decrescente.

claudinho_confirm : notificacao de confirm nos 5 minutos anteriores ao trade
claudinho_loop : notificacao de loop (top5/cascade/spark/roar) nos 10 minutos
anteriores, sem confirm no mesmo simbolo ignorou_veto : veto em scan_results nos
10 minutos anteriores, sem nenhum sinal — subconjunto de olho na agregacao olho
: nenhuma correspondencia

Racional: confirm tem prioridade sobre loop porque o operador rodou validacao
explicita antes de entrar. Janelas diferentes por protocolo refletem o fluxo
real — confirm e imediato (< 5 min), loop pode demorar ate o operador avaliar
(ate 10 min). Ig.Veto e subconjunto de olho na agregacao mas coluna separada na
tabela — permite identificar quando o operador entrou contra o veto do 1h e
medir o impacto dessa decisao isoladamente.

Alternativas descartadas: janela unica de 30 minutos para todos os protocolos.
Descartada por ser larga demais e associar trades independentes a sinais
antigos. Janela de 5 minutos para loop. Descartada porque o operador pode
demorar para avaliar e entrar apos uma notificacao de loop.

## [DEC-024] 2026-03-26 - Relatorio de analise em monospace com send_message_pre

Decisao: relatorio do Claudinho analisa enviado em bloco HTML pre via
send_message_pre, separado do send_message usado pelos outros protocolos.

Racional: tabelas markdown nao renderizam no Telegram. Monospace com HTML pre
preserva alinhamento de colunas e entrega o relatorio legivel sem alterar o
parse_mode dos outros formatadores.

Alternativas descartadas: alterar parse_mode global de send_message. Descartado
por risco de quebrar formatacao dos outros protocolos.

## [DEC-025] 2026-03-26 - Saldo da carteira via API autenticada em tempo real

Decisao: o relatorio de analise busca o saldo disponivel em USDT via GET
/fapi/v2/balance a cada execucao, em vez de usar valor configurado em .env.

Racional: o operador faz saques e depositos com frequencia. Um valor fixo em
.env ficaria desatualizado rapidamente e tornaria a variacao percentual
imprecisa. A busca em tempo real reflete a realidade da carteira no momento da
analise.

Alternativas descartadas: BANK_USDT em .env. Descartado por exigir atualizacao
manual a cada movimentacao financeira.

```
---

**Commit message:**
```

feat: analyzer expandido — 4 categorias, tabela monospace, saldo real

Classificacao de trades em claudinho_confirm (5min), claudinho_loop (10min),
ignorou_veto (subconjunto olho) e olho. Confirm tem prioridade sobre loop.
Ig.Veto isola entradas contra veto do 1h.

Relatorio em tabela monospace via send_message_pre (HTML pre). Saldo USDT
buscado em tempo real via /fapi/v2/balance. Timezone corrigido para
America/Sao_Paulo no header. Valores numericos com 2 casas decimais.
format_confirm persiste em notifications_sent independente do score.

---

## [DEC-022] 2026-03-26 - Corte de volume minimo unificado em $2M para todos os protocolos

Decisao: reduzir o filtro de volume minimo 24h para $2M em todos os protocolos
(Top5, Cascade, Roar, Spark).

Racional: o corte anterior ($10M-$30M) estava eliminando entradas reais em
ativos com liquidez suficiente para day trade de curto prazo. Analise da lista
completa de perpetuos USDT-M confirmou volume significativo de oportunidades
entre $2M e $30M sendo descartadas antes dos filtros tecnicos atuarem.

Os protocolos sao tecnicamente robustos o suficiente para rejeitar ativos sem
condicao via indicadores — o filtro de volume nao precisa compensar ausencia de
filtro tecnico. Em day trade de 1-4h, liquidez de $2M e suficiente para execucao
sem impacto relevante nas posicoes do tamanho operado.

Alternativas descartadas: cortes diferenciados por protocolo ($5M Top5, $2M
Cascade, $10M Roar). Descartado para manter uniformidade e permitir medicao
comparativa limpa do desempenho do agente nesta fase.

```
---

**Commit message:**
```

refactor: volume minimo unificado em $2M em todos os protocolos

Top5: $30M -> $2M Cascade: $10M -> $2M Roar: $30M -> $2M Spark: $1M -> $2M
(maximo preservado em $50M)

Corte alto eliminava entradas reais antes dos filtros tecnicos atuarem.
Protocolos sao robustos o suficiente para fazer esse trabalho. Uniformidade
facilita medicao comparativa do agente.

---

## [0.5.0] - 2026-03-26

### Adicionado

- src/roar_hunter.py: scanner do protocolo Roar Hunter

### Protocolo Roar Hunter (v1)

- Universo: perpetuos USDT-M com volume > $30M e variacao 24h <= +3% — ativos
  que caíram ou ficaram parados, excluindo quem ja subiu
- Filtro de vitalidade: soma das ultimas 3 velas de 1h >= 20% acima da soma das
  3 velas anteriores — descarta ativos sem acumulo real de volume recente
- 1h como coracao do protocolo (nao veto): BB spread > 10%, ambas as bandas
  apontando pra cima, close abaixo do BB mid, MACD histograma positivo, TSI
  positivo e ascendente, StochRSI K >= 40 e ascendente
- Veto direto: StochRSI cruzado pra baixo no 1h — movimento de exaustao
- Veto direto: close acima de 70% do range BB no 1h — movimento ja consumido
- Analise historica de ciclos MACD nos 100 candles do 1h: identifica cruzamentos
  validos (histograma positivo por >= 3 candles consecutivos), mede amplitude
  maxima nos 20 candles seguintes, concede bonus +1 se algum ciclo atingiu >= 7%
  e exibe o historico no output como campo informativo
- 15m como confirmacao de direcao: BB ascendente, TSI positivo e ascendente,
  MACD positivo
- 5m como confirmacao de energia: volume acima da MA20 por fator 1.2x, MACD
  positivo e ascendente
- SL: banda inferior da BB do 1h
- Trailing CB: 2% fixo (horizonte de swing de 2-4h)
- Score maximo: 13 pontos (7 no 1h + 1 bonus historico + 3 no 15m + 2 no 5m)
- Score minimo para output: 9
- Output: top 5 ativos em ordem de score

### Modificado

- src/notifier.py: format_roar() adicionado, persistencia em scan_results e
  notifications_sent para o protocolo Roar
- src/runner.py: thread run_roar adicionada, Roar incluido no run_once, env var
  SCAN_INTERVAL_ROAR (default 30 min), mensagem de startup atualizada

### Variaveis de ambiente adicionadas

- SCAN_INTERVAL_ROAR: intervalo do loop Roar em minutos (default 30)

---

## [DEC-020] 2026-03-23 - Janela de correlacao trade-notificacao: 5 minutos

Decisao: um trade e classificado como "claudinho" se existe notificacao para o
mesmo simbolo nos 5 minutos anteriores ao horario do trade.

Racional: o objetivo do claudinho e ser um agente passivo que substitui a
presenca constante na tela. Quando o operador age sobre uma notificacao, age
rapidamente — abre a Binance, avalia e entra. 5 minutos e o teto realista para
esse fluxo. Uma janela maior geraria falsos positivos (notificacoes antigas
associadas a trades independentes).

Alternativas descartadas: janela de 30 minutos. Descartada por ser larga demais
e associar trades "no olho" a notificacoes distantes no tempo.

---

## [DEC-019] 2026-03-23 - Classificacao binaria de trades: claudinho vs olho

Decisao: cada trade e classificado como "claudinho" (existia notificacao no
simbolo nos 5 min anteriores) ou "olho" (sem notificacao correspondente). Nao
existe categoria intermediaria para "confirm manual sem notificacao de loop".

Racional: a granularidade binaria e suficiente para o objetivo principal —
comparar a performance dos trades guiados pelo agente com os trades por
julgamento proprio. Adicionar uma terceira categoria (confirm manual)
complicaria a analise sem beneficio proporcional neste estagio.

Alternativas descartadas: categoria separada para "confirm manual". Descartada
por adicionar complexidade ao cruzamento sem alterar o insight central.

---

## [DEC-018] 2026-03-23 - Endpoint /fapi/v1/income para historico de trades

Decisao: usar GET /fapi/v1/income com incomeType=REALIZED_PNL para buscar
historico de performance, em vez de GET /fapi/v1/userTrades.

Racional: /fapi/v1/userTrades requer o parametro symbol e so cobre janelas de
ate 7 dias por chamada, exigindo uma requisicao por simbolo operado. O endpoint
/income retorna PnL realizado de todos os simbolos em uma unica chamada, com
paginacao por timestamp e suporte a janelas de ate 30 dias.

Alternativas descartadas: /fapi/v1/userTrades por simbolo. Descartado por
requerer multiplas chamadas e nao cobrir periodos de 30 dias sem iteracao
complexa.

---

## [DEC-017] 2026-03-23 - Supabase via REST API sem biblioteca cliente

Decisao: a integracao com o Supabase e feita via requests diretamente para a
REST API do Supabase (PostgREST), sem instalar a biblioteca supabase-py.

Racional: o projeto ja usa requests como unica dependencia de HTTP. A API REST
do Supabase e simples e bem documentada. Adicionar supabase-py introduziria
dependencias transitivas (httpx, gotrue, realtime) sem beneficio real para o
caso de uso atual (insert, upsert, select com filtros simples).

Alternativas descartadas: supabase-py. Descartado por peso desnecessario de
dependencias para operacoes basicas de CRUD.

---

## [DEC-016] 2026-03-22 - Horario de operacao automatica

Decisao: os loops so disparam notificacoes automaticas dentro de janelas de
horario definidas (seg-sex 06:00-23:59, dom 20:00-23:59). Sabado e fora dessas
janelas: somente sob demanda via comando Telegram. Timezone: America/Sao_Paulo.

Racional: o operador nao quer ser acordado por notificacoes no meio da
madrugada. O mercado de futuros opera 24h mas o operador nao — o agente deve
respeitar o ritmo humano de operacao.

O comando "Claudinho roda os protocolos" ignora o horario e dispara uma rodada
imediata, permitindo acesso sob demanda a qualquer momento.

Alternativas descartadas: rodar sem restricao de horario. Descartado por gerar
ruido desnecessario fora do horario de operacao do trader.

---

## [DEC-015] 2026-03-22 - Cooldown em memoria, sem persistencia

Decisao: o estado de cooldown por ativo e mantido em dicionario Python em
memoria. Nao e persistido em disco nem em banco de dados nesta fase.

Racional: o runner e um processo continuo. Reinicializacoes sao raras e um
cooldown zerado apos restart e aceitavel — no pior caso o operador recebe uma
notificacao duplicada. Persistencia adiciona complexidade sem beneficio
proporcional neste estagio.

Alternativas descartadas: persistir cooldown em arquivo JSON ou Supabase.
Descartado para esta fase. Sera revisado se restarts frequentes gerarem ruido.

---

## [DEC-014] 2026-03-22 - Loop em runner.py separado dos scanners

Decisao: o orquestrador de loops mora em runner.py, arquivo novo. Os scanners
existentes (top5_hunter, cascade_market_reader, spark_market_reader) permanecem
inalterados e continuam funcionais como scripts standalone.

Racional: separacao de responsabilidades. O scanner nao deve saber que esta
sendo chamado por um loop ou por um humano no terminal. O runner e o unico
responsavel por scheduling, cooldown e notificacao.

Alternativas descartadas: adicionar loop diretamente dentro de cada scanner via
flag de argumento. Descartado por acoplamento desnecessario entre logica de
mercado e logica de orquestracao.

---

## [DEC-013] 2026-03-22 - Polling Telegram via requests puro

Decisao: o polling do Telegram e feito diretamente via requests para a API REST
do Telegram, sem uso da biblioteca python-telegram-bot.

Racional: o projeto ja usa requests como unica dependencia de HTTP. Adicionar
python-telegram-bot introduziria uma dependencia pesada com async e event loop
proprio, incompativel com o modelo de threading adotado. A API do Telegram e
simples o suficiente para ser consumida diretamente.

Alternativas descartadas: python-telegram-bot com polling asyncio. Descartado
por incompatibilidade com threading e complexidade desnecessaria para o volume
de comandos esperado.

---

## [DEC-012] 2026-03-18 - Protocolo Spark: deteccao de compressao e gatilho PAH

Decisao: criar protocolo independente para capturar explosoes de ativos
esquecidos que saem do nada com volume e momentum.

Universo: 250 a 400 ativos com volume 24h entre $1M e $50M e variacao entre -8%
e +8%. Sao os ativos fora do radar — nem top nem bottom — onde energia se
acumula sem visibilidade.

Logica em tres fases: 1h + 15m: BBW no bottom 25% do historico proprio
(compressao real) 5m: corpo medio, fechando pra cima, volume crescendo, preco
encostando na banda 1m: volume 3x acima da media, corpo cheio, rompimento da
banda superior (PAH)

Callback Spark: 3% se spread BB menor que 5%, 5% se maior.

Alternativas descartadas: incluir esses ativos no Cascade. Descartado porque o
Cascade busca momentum ja visivel — o Spark busca o momento antes do movimento
aparecer no radar.

---

## [DEC-011] 2026-03-18 - Gatilho do 5m: MACD pre-cruzamento

Decisao: o gatilho do 5m aceita MACD ainda negativo desde que ascendente e com
recovery de pelo menos 30% do minimo recente (janela de 10 velas). MACD positivo
continua sendo aceito se ascendente.

Racional: o sweet spot de entrada identificado pelo operador e o MACD subindo em
direcao ao zero com StochRSI e TSI ja folgados pra cima. Exigir MACD positivo no
5m atrasa a entrada e reduz o upside disponivel.

Alternativas descartadas: exigir MACD positivo e ascendente no 5m.

---

## [DEC-010] 2026-03-18 - 1h reformulado como veto puro no Cascade

Decisao: o filtro do 1h deixou de ser confirmacao e passou a ser veto puro.
Rejeita apenas se MA7 abaixo de MA99 ou MACD claramente negativo.

Racional: o 1h como confirmacao eliminava entradas validas em tendencias em
formacao. Na pratica funciona como freio de mao — so muda de ideia se o grafico
parecer outro ativo.

Alternativas descartadas: manter MA7 > MA25 > MA99 como requisito no 1h.

---

## [DEC-009] 2026-03-17 - Aviso de SL acima de 8%

Decisao: quando o SL calculado resultar em distancia acima de 8% do preco de
entrada, o scanner exibe aviso. O setup nao e descartado.

Racional: com spreads altos de Bollinger, o SL natural pode chegar a 11% ou mais
— tecnicamente correto mas potencialmente incompativel com a alavancagem em uso.
O operador decide se entra com o SL real da banda ou trava em 8%.

Alternativas descartadas: descartar automaticamente setups com SL acima de 8%.

---

## [DEC-008] 2026-03-17 - Correlacao BTC como camada de filtro no 5m e 15m

Decisao: adicionar correlacao de Pearson (janela 20 velas) entre o ativo e o BTC
nos timeframes de 5m e 15m como camada obrigatoria do Cascade. Dois casos
permitidos: Caso A (aligned): correlacao acima de 0.6 Caso B (independent):
correlacao abaixo de 0.4 Zona morta (0.4 a 0.6): descartada.

Alternativas descartadas: correlacao unica no 1h. Descartada porque em 1h o BTC
mascara movimentos proprios das altcoins.

---

## [DEC-007] 2026-03-17 - StochRSI sobrecompra condicional no 15m

Decisao: o limite de 80 no StochRSI do 15m e dispensado quando o 1h tem MA7
acima de MA99. Com tendencia forte no 1h, StochRSI acima de 80 indica
combustivel aceso, nao exaustao.

Alternativas descartadas: manter limite fixo de 80 em todos os casos.

---

## [DEC-006] 2026-03-17 - Fase 1 sem execucao de ordens

Decisao: a Fase 1 e somente leitura. Nenhuma ordem e enviada a Binance.

Racional: antes de confiar capital a qualquer agente automatizado, e necessario
validar que a logica de identificacao de setup esta correta e alinhada com o
julgamento do operador.

---

## [DEC-005] 2026-03-17 - Sem TP fixo

Decisao: os protocolos Cascade e Spark nao definem Take Profit. O trailing stop
faz o trabalho de saida.

Racional: TP fixo limita o upside em movimentos de momentum real.

---

## [DEC-004] 2026-03-17 - Universo de ativos Cascade: top 30 e bottom 30 dinamico

Decisao: o scanner nao opera com lista fixa de simbolos. A cada execucao, busca
os top 30 e bottom 30 simbolos USDT por variacao nas ultimas 24h com volume
minimo de $10M.

Racional: os ativos com maior momentum mudam constantemente. Uma lista fixa
perde oportunidades e carrega ativos mortos.

---

## [DEC-003] 2026-03-17 - Callback do trailing via spread Bollinger

Decisao: callback de 1% se spread BB no 5m for menor que 5%, callback de 2% se
igual ou maior que 5%.

Racional: em mercados de baixa volatilidade, callback de 2% queima o trailing
antes do movimento se completar. Em alta volatilidade, callback de 1% e acionado
por ruido normal.

---

## [DEC-002] 2026-03-17 - SL dinamico via banda inferior da Bollinger

Decisao: o stop loss nao e um percentual fixo. E o preco da banda inferior da
Bollinger no 5m no momento da entrada.

Racional: a banda inferior representa o limite estatistico do movimento dentro
da volatilidade corrente — se o preco rompe abaixo dela, a tese do trade
quebrou.

---

## [DEC-001] 2026-03-17 - Protocolo primario: Cascade

Decisao: implementar um unico protocolo no MVP em vez de todos os sete
protocolos existentes.

Racional: complexidade prematura e inimiga da validacao. O Cascade foi escolhido
por ter as condicoes de entrada mais objetivas e mensuraveis entre os protocolos
disponiveis.
