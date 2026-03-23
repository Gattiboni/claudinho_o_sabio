# DECISION LOG

Registro de decisoes de arquitetura, design e protocolo. Cada entrada documenta
o que foi decidido, por que, e quais alternativas foram descartadas.

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
