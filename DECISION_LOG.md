# DECISION LOG

Registro de decisoes de arquitetura, design e protocolo. Cada entrada documenta
o que foi decidido, por que, e quais alternativas foram descartadas.

---

## [DEC-001] 2026-03-17 - Protocolo primario: Cascade

**Decisao:** Implementar um unico protocolo no MVP em vez de todos os sete
protocolos existentes.

**Racional:** Complexidade prematura e inimiga da validacao. Um protocolo bem
implementado e testavel e mais util do que sete implementados pela metade. O
Cascade foi escolhido por ter as condicoes de entrada mais objetivas e
mensuráveis entre os protocolos disponiveis.

**Alternativas descartadas:** Implementar GEM, BVE ou PBS como protocolo
primario. Descartados porque o Cascade foi desenhado especificamente para o
contexto de maior sucesso do operador: momentum real em altcoins com confirmacao
multi-timeframe.

---

## [DEC-002] 2026-03-17 - SL dinamico via banda inferior da Bollinger

**Decisao:** O stop loss nao e um percentual fixo. E o preco da banda inferior
da Bollinger no 5min no momento da entrada.

**Racional:** Um percentual fixo e arbitrario e ignora o estado atual do
mercado. A banda inferior da Bollinger representa o limite estatistico do
movimento dentro da volatilidade corrente — se o preco rompe abaixo dela, a tese
do trade quebrou independentemente de qualquer percentual.

**Alternativas descartadas:** SL fixo de 3%, 5% ou 8%. Descartados por serem
arbitrarios e nao responsivos ao contexto do ativo no momento da entrada.

---

## [DEC-003] 2026-03-17 - Callback do trailing via spread Bollinger

**Decisao:** Callback de 1% se spread BB no 5min for menor que 5%, callback de
2% se igual ou maior que 5%.

**Racional:** Em mercados de baixa volatilidade, callback de 2% queima o
trailing antes do movimento se completar. Em mercados de alta volatilidade,
callback de 1% e acionado por ruido normal do preco. O spread da Bollinger e o
termometro de volatilidade mais imediato disponivel — o mesmo instrumento que
mede o espaco do trade define a folga do trailing.

**Alternativas descartadas:** Callback fixo de 1% ou 2% independente do
contexto. Descartados por nao se adaptarem ao regime de volatilidade do momento.

---

## [DEC-004] 2026-03-17 - Universo de ativos: top 30 e bottom 30 dinamico

**Decisao:** O scanner nao opera com lista fixa de simbolos. A cada execucao,
busca os top 30 e bottom 30 simbolos USDT por variacao nas ultimas 24h com
volume minimo de $10M.

**Racional:** Os ativos com maior momentum mudam constantemente. Uma lista fixa
perde oportunidades e carrega ativos mortos. O bottom 30 foi incluido
deliberadamente — ativos com queda forte e reversao confirmada pelos indicadores
representam assimetria real.

**Alternativas descartadas:** Lista fixa de 8 a 20 altcoins selecionadas
manualmente. Descartada por ser estatica e requerer manutencao constante.

---

## [DEC-005] 2026-03-17 - Sem TP fixo

**Decisao:** O protocolo Cascade nao define Take Profit. O trailing stop faz o
trabalho de saida.

**Racional:** TP fixo limita o upside em movimentos de momentum real, que sao
exatamente os que o Cascade busca capturar. O trailing deixa o mercado definir o
tamanho do lucro enquanto protege o capital acumulado.

**Alternativas descartadas:** TP fixo entre 2% e 5%. Descartado porque impoe
teto artificial em trades que poderiam render substancialmente mais.

---

## [DEC-006] 2026-03-17 - Fase 1 sem execucao de ordens

**Decisao:** A Fase 1 e somente leitura. Nenhuma ordem e enviada a Binance.
Nenhuma API key autenticada e usada.

**Racional:** Antes de confiar capital a qualquer agente automatizado, e
necessario validar que a logica de identificacao de setup esta correta e
alinhada com o julgamento do operador. A validacao acontece comparando os setups
identificados pelo scanner com a leitura manual do operador ao longo de sessoes
reais.

**Alternativas descartadas:** Comecar diretamente com execucao em conta real ou
testnet. Descartado por pular a etapa de validacao da logica de entrada.

---

[DEC-007] StochRSI sobrecompra condicional no 15m

Decisao: o limite de 80 no StochRSI do 15m e dispensado quando o 1h tem MA7 >
MA25 > MA99 alinhadas. Com tendencia forte no 1h, StochRSI acima de 80 no 15m
indica combustivel aceso, nao exaustao. O limite se aplica apenas quando o 1h
nao tem alinhamento completo de MAs.

---

## [DEC-007] 2026-03-17 - StochRSI sobrecompra condicional no 15m

Decisao: o limite de 80 no StochRSI do 15m e dispensado quando o 1h tem MA7 >
MA25 > MA99 alinhadas. Com tendencia forte no 1h, StochRSI acima de 80 no 15m
indica combustivel aceso, nao exaustao. O limite se aplica apenas quando o 1h
nao tem alinhamento completo de MAs.

Alternativas descartadas: manter limite fixo de 80 em todos os casos. Descartado
apos validacao empirica com GRASSUSDT — ativo em momentum real com StochRSI
acima de 80 no 15m que performou +50% na sessao.

## [DEC-008] 2026-03-17 - Correlacao BTC como camada de filtro no 5m e 15m

Decisao: adicionar correlacao de Pearson (janela 20 velas) entre o ativo e o BTC
nos timeframes de 5m e 15m como camada obrigatoria do Cascade. Dois casos
permitidos:

Caso A (aligned): correlacao > 0.7 — ativo andando junto com BTC forte Caso B
(independent): correlacao < 0.3 — ativo com vida propria, ignorando BTC

Zona morta (entre 0.3 e 0.7) e descartada: sem sinal claro de relacao ou
independencia, o movimento nao e confiavel para o Cascade.

O filtro nao se aplica ao 1h — no macro, o BTC domina o sinal de qualquer
altcoin e eliminaria oportunidades validas. A correlacao e relevante apenas nas
janelas curtas onde o comportamento independente e detectavel e operavel.

Alternativas descartadas: correlacao unica no 1h. Descartada porque em 1h o BTC
mascara movimentos proprios das altcoins.

## [DEC-009] 2026-03-17 - Aviso de SL acima de 8%

Decisao: quando o SL calculado (banda inferior BB no 5m) resultar em distancia
acima de 8% do preco de entrada, o scanner exibe aviso e sugere teto de -8% como
referencia. O setup nao e descartado.

Racional: com spreads altos de Bollinger (ex: 13%), o SL natural pode chegar a
11% ou mais — tecnicamente correto mas potencialmente incompativel com a
alavancagem em uso. O operador decide no olho se entra com o SL real da banda ou
trava em 8%.

Alternativas descartadas: descartar automaticamente setups com SL acima de 8%.
Descartado para nao eliminar oportunidades validas em ativos de alta
volatilidade onde o spread largo e parte do setup.
