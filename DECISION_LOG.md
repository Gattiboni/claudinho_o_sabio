# DECISION LOG

Registro de decisoes de arquitetura, design e protocolo. Cada entrada documenta
o que foi decidido, por que, e quais alternativas foram descartadas.

---

## [DEC-001] 2026-03-17 - Protocolo primario: Cascade

Decisao: implementar um unico protocolo no MVP em vez de todos os sete
protocolos existentes.

Racional: complexidade prematura e inimiga da validacao. Um protocolo bem
implementado e testavel e mais util do que sete implementados pela metade. O
Cascade foi escolhido por ter as condicoes de entrada mais objetivas e
mensuraveis entre os protocolos disponiveis.

Alternativas descartadas: implementar GEM, BVE ou PBS como protocolo primario.
Descartados porque o Cascade foi desenhado especificamente para o contexto de
maior sucesso do operador: momentum real em altcoins com confirmacao
multi-timeframe.

---

## [DEC-002] 2026-03-17 - SL dinamico via banda inferior da Bollinger

Decisao: o stop loss nao e um percentual fixo. E o preco da banda inferior da
Bollinger no 5m no momento da entrada.

Racional: um percentual fixo e arbitrario e ignora o estado atual do mercado. A
banda inferior da Bollinger representa o limite estatistico do movimento dentro
da volatilidade corrente — se o preco rompe abaixo dela, a tese do trade quebrou
independentemente de qualquer percentual.

Alternativas descartadas: SL fixo de 3%, 5% ou 8%. Descartados por serem
arbitrarios e nao responsivos ao contexto do ativo no momento da entrada.

---

## [DEC-003] 2026-03-17 - Callback do trailing via spread Bollinger

Decisao: callback de 1% se spread BB no 5m for menor que 5%, callback de 2% se
igual ou maior que 5%.

Racional: em mercados de baixa volatilidade, callback de 2% queima o trailing
antes do movimento se completar. Em mercados de alta volatilidade, callback de
1% e acionado por ruido normal do preco. O spread da Bollinger e o termometro de
volatilidade mais imediato disponivel.

Alternativas descartadas: callback fixo de 1% ou 2% independente do contexto.
Descartados por nao se adaptarem ao regime de volatilidade do momento.

---

## [DEC-004] 2026-03-17 - Universo de ativos Cascade: top 30 e bottom 30 dinamico

Decisao: o scanner nao opera com lista fixa de simbolos. A cada execucao, busca
os top 30 e bottom 30 simbolos USDT por variacao nas ultimas 24h com volume
minimo de $10M.

Racional: os ativos com maior momentum mudam constantemente. Uma lista fixa
perde oportunidades e carrega ativos mortos. O bottom 30 foi incluido
deliberadamente — ativos com queda forte e reversao confirmada pelos indicadores
representam assimetria real.

Alternativas descartadas: lista fixa de 8 a 20 altcoins selecionadas
manualmente. Descartada por ser estatica e requerer manutencao constante.

---

## [DEC-005] 2026-03-17 - Sem TP fixo

Decisao: os protocolos Cascade e Spark nao definem Take Profit. O trailing stop
faz o trabalho de saida.

Racional: TP fixo limita o upside em movimentos de momentum real. O trailing
deixa o mercado definir o tamanho do lucro enquanto protege o capital acumulado.

Alternativas descartadas: TP fixo entre 2% e 5%. Descartado porque impoe teto
artificial em trades que poderiam render substancialmente mais.

---

## [DEC-006] 2026-03-17 - Fase 1 sem execucao de ordens

Decisao: a Fase 1 e somente leitura. Nenhuma ordem e enviada a Binance. Nenhuma
API key autenticada e usada.

Racional: antes de confiar capital a qualquer agente automatizado, e necessario
validar que a logica de identificacao de setup esta correta e alinhada com o
julgamento do operador.

Alternativas descartadas: comecar diretamente com execucao em conta real ou
testnet. Descartado por pular a etapa de validacao da logica de entrada.

---

## [DEC-007] 2026-03-17 - StochRSI sobrecompra condicional no 15m

Decisao: o limite de 80 no StochRSI do 15m e dispensado quando o 1h tem MA7
acima de MA99. Com tendencia forte no 1h, StochRSI acima de 80 no 15m indica
combustivel aceso, nao exaustao. O limite se aplica apenas quando o 1h nao tem
alinhamento estrutural de MAs.

Alternativas descartadas: manter limite fixo de 80 em todos os casos. Descartado
apos validacao empirica com GRASSUSDT — ativo em momentum real com StochRSI
acima de 80 no 15m que performou +50% na sessao.

---

## [DEC-008] 2026-03-17 - Correlacao BTC como camada de filtro no 5m e 15m

Decisao: adicionar correlacao de Pearson (janela 20 velas) entre o ativo e o BTC
nos timeframes de 5m e 15m como camada obrigatoria do Cascade. Dois casos
permitidos:

  Caso A (aligned): correlacao acima de 0.6 — ativo andando junto com BTC forte
  Caso B (independent): correlacao abaixo de 0.4 — ativo com vida propria

Zona morta (entre 0.4 e 0.6) e descartada: sem sinal claro de relacao ou
independencia, o movimento nao e confiavel para o Cascade.

O filtro nao se aplica ao 1h — no macro, o BTC mascara movimentos proprios das
altcoins e eliminaria oportunidades validas.

Alternativas descartadas: correlacao unica no 1h. Descartada porque em 1h o BTC
mascara movimentos proprios das altcoins.

---

## [DEC-009] 2026-03-17 - Aviso de SL acima de 8%

Decisao: quando o SL calculado (banda inferior BB no 5m) resultar em distancia
acima de 8% do preco de entrada, o scanner exibe aviso e sugere teto de -8% como
referencia. O setup nao e descartado.

Racional: com spreads altos de Bollinger, o SL natural pode chegar a 11% ou mais
— tecnicamente correto mas potencialmente incompativel com a alavancagem em uso.
O operador decide no olho se entra com o SL real da banda ou trava em 8%.

Alternativas descartadas: descartar automaticamente setups com SL acima de 8%.
Descartado para nao eliminar oportunidades validas em ativos de alta volatilidade
onde o spread largo e parte do setup.

---

## [DEC-010] 2026-03-18 - 1h reformulado como veto puro no Cascade

Decisao: o filtro do 1h deixou de ser confirmacao (MA alinhada + MACD positivo)
e passou a ser veto puro. Rejeita apenas se MA7 abaixo de MA99 (inversao
estrutural) ou MACD claramente negativo (abaixo de 50% da media do valor absoluto
historico). Tudo mais passa.

Racional: o 1h como confirmacao eliminava entradas validas em tendencias em
formacao. Na pratica do operador, o 1h funciona como freio de mao — so muda de
ideia se o grafico parecer outro ativo. Exigir alinhamento completo de MAs no 1h
e prematuro para o estilo de entrada do Cascade.

Alternativas descartadas: manter MA7 > MA25 > MA99 como requisito no 1h.
Descartado apos validacao com IRUSDT — ativo com MA99 ainda negativa mas com
movimento de +135% ja em andamento.

---

## [DEC-011] 2026-03-18 - Gatilho do 5m: MACD pre-cruzamento

Decisao: o gatilho do 5m aceita MACD ainda negativo desde que ascendente e com
recovery de pelo menos 30% do minimo recente (janela de 10 velas). MACD positivo
continua sendo aceito se ascendente.

Racional: o sweet spot de entrada identificado pelo operador e o MACD subindo em
direcao ao zero com StochRSI e TSI ja folgados pra cima. No 1m isso ja aparece
como MACD positivo recente. Exigir MACD positivo no 5m atrasa a entrada e reduz
o upside disponivel.

Alternativas descartadas: exigir MACD positivo e ascendente no 5m. Descartado
porque elimina entradas antes do cruzamento, que sao exatamente as de maior
assimetria.

---

## [DEC-012] 2026-03-18 - Protocolo Spark: deteccao de compressao e gatilho PAH

Decisao: criar protocolo independente para capturar explosoes de ativos
esquecidos que saem do nada com volume e momentum.

Universo: 250 a 400 ativos com volume 24h entre $1M e $50M e variacao entre -8%
e +8%. Sao os ativos fora do radar — nem top nem bottom — onde energia se acumula
sem visibilidade.

Logica em tres fases:
  1h + 15m: BBW no bottom 25% do historico proprio (compressao real)
  5m: corpo medio, fechando pra cima, volume crescendo, preco encostando na banda
  1m: volume 3x acima da media, corpo cheio, rompimento da banda superior (PAH)

Callback Spark: 3% se spread BB menor que 5%, 5% se maior (maior folga que o
Cascade porque o movimento e mais explosivo e menos previsivel).

Alternativas descartadas: incluir esses ativos no Cascade. Descartado porque o
Cascade busca momentum ja visivel — o Spark busca o momento antes do movimento
aparecer no radar.