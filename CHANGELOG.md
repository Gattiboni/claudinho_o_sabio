# CHANGELOG

Todas as mudancas relevantes do projeto serao documentadas aqui. Formato baseado
em Keep a Changelog (https://keepachangelog.com).

---

## [0.6.0] - 2026-03-27

### Adicionado

- src/position_fetcher.py: busca posicao aberta na Binance Futures via
  /fapi/v2/positionRisk e calcula contexto de mercado (BB, MACD, StochRSI em 15m
  e 5m) para uso pelo rescue_protocol
- src/rescue_protocol.py: protocolo E Agora — acionado por comando Telegram,
  busca posicao aberta, chama Claude API e entrega 2 cenarios de gestao de risco
  diretamente no chat

### Modificado

- src/analyzer.py: classificacao de trades expandida com categoria rescue —
  trades fechados ou abertos em ate 60 minutos apos pedido E agora
- src/analyzer.py: relatorio com cinco colunas (Geral, Claudinho, Rescue,
  Ig.Veto, Olho) e comparativo Rescue vs Olho em win rate
- src/runner.py: handle_rescue adicionado, comando "Claudinho e agora? SYMBOL"
  registrado em process_message

### Protocolo E Agora (v1)

- Acionado por: "Claudinho e agora? SYMBOL"
- Busca posicao aberta via /fapi/v2/positionRisk: entry, mark, PnL, leverage,
  margin, liquidation
- Calcula BB (upper/middle/lower/spread/rising), MACD e StochRSI em 15m e 5m
  nativamente via pandas/numpy — sem novas dependencias
- Monta prompt estruturado com todos os dados e chama Claude API
  (claude-sonnet-4-20250514, max_tokens=700)
- Resposta em portugues: 2 cenarios situacionais com acao (precos especificos),
  racional e risco
- Leque de cenarios avaliados pelo modelo: fechar imediatamente, fechar 50% e
  segurar, estender SL para BB lower do 5m, estender SL para BB lower do 15m,
  fechar e recomprar no fundo com 2x-5x o tamanho, aguardar bounce no oversold
- Persiste em scan_results (dados da posicao no momento) e notifications_sent
  com protocol="rescue" para rastreamento no analyzer

### Variaveis de ambiente adicionadas

- ANTHROPIC_API_KEY: chave da API Anthropic para chamadas do rescue_protocol

---

## [0.5.2] - 2026-03-26

### Modificado

- src/analyzer.py: classificacao de trades expandida para quatro categorias
- src/analyzer.py: correcao de timezone no header do relatorio
  (America/Sao_Paulo)
- src/analyzer.py: todos os valores numericos com 2 casas decimais
- src/analyzer.py: busca de saldo USDT via API autenticada da Binance em tempo
  real
- src/analyzer.py: tabela do relatorio em formato monospace com colunas
  alinhadas
- src/notifier.py: send_message_pre adicionada para envio de relatorios em HTML
  pre
- src/notifier.py: format_confirm persiste em notifications_sent independente do
  score
- src/runner.py: handle_analysis usa send_message_pre para entrega tabular no
  Telegram

---

## [0.5.1] - 2026-03-26

### Modificado

- src/top5_hunter.py: VOLUME_MIN_24H_USD reduzido de $30M para $2M
- src/cascade_market_reader.py: VOLUME_MIN_24H_USD reduzido de $10M para $2M
- src/roar_hunter.py: VOLUME_MIN_24H_USD reduzido de $30M para $2M
- src/spark_universe.py: VOLUME_MIN_24H_USD reduzido de $1M para $2M
  (VOLUME_MAX_24H_USD preservado em $50M)

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

## [0.4.0] - 2026-03-23

### Adicionado

- src/supabase_client.py: cliente HTTP para o Supabase REST API (insert, upsert,
  select, select_range com paginacao automatica)
- src/binance_auth.py: assinatura HMAC SHA256 para endpoints autenticados da
  Binance Futures
- src/trade_fetcher.py: busca REALIZED_PNL via GET /fapi/v1/income e persiste na
  tabela trades do Supabase
- src/analyzer.py: analise de performance por periodo com classificacao de
  trades por origem (claudinho vs olho)
- Tabelas Supabase criadas: scan_results, notifications_sent, trades
- Projeto Supabase: claudinho_o_sabio (ID: lwvkdvatmdvsogvemwcq, regiao:
  Americas)

### Fase 2b - Persistencia e Analise

- Cada notificacao enviada e persistida em notifications_sent com protocol,
  symbol, score, message_text, triggered_by
- Cada sinal identificado pelos scanners e persistido em scan_results com
  details_json
- Trades buscados via API autenticada da Binance (/fapi/v1/income,
  incomeType=REALIZED_PNL) e persistidos em trades
- Paginacao automatica no Supabase: busca em blocos de 1000 registros ate
  esgotar o periodo
- Timestamp da Binance sincronizado via /fapi/v1/time para evitar erro -1021
- Classificacao automatica de trades: cruza trades com notificacoes por simbolo
  em janela de 5 minutos
  - Notificacao + trade no mesmo simbolo em ate 5 min: categoria "claudinho"
  - Trade sem notificacao correspondente: categoria "olho"
  - Notificacao sem trade correspondente: ignorada na analise
- KPIs calculados por categoria: total de trades, win rate, PnL bruto, PnL
  liquido, maior ganho/perda, media ganho/perda
- Comparativo claudinho vs olho em win rate quando ambas as categorias tem
  trades

### Comando Telegram adicionado

- "Claudinho analisa": abre menu de selecao de periodo (24h / 3d / 7d / 30d),
  busca trades da Binance, persiste no Supabase e envia relatorio completo

### Variaveis de ambiente adicionadas

- SUPABASE_URL: URL do projeto Supabase
- SUPABASE_ANON_KEY: chave publica do Supabase para acesso via REST API

### Deploy Railway

- Regiao alterada de US East (Virginia) para EU West (Amsterdam) para resolver
  bloqueio HTTP 451 da Binance
- RAILPACK_START_CMD adicionado nas variaveis de ambiente do Railway

---

## [0.3.0] - 2026-03-22

### Adicionado

- src/notifier.py: camada de notificacao via Telegram
- src/runner.py: orquestrador principal com loops independentes por protocolo
- src/confirm.py: funcao analyze_to_dict() adicionada para uso pelo runner e
  notifier
- pyrightconfig.json: configuracao do Pylance com typeCheckingMode off

### Fase 2a - Notificacoes via Telegram

- Bot Telegram configurado via @BotFather (@claudinho_o_sabio_bot)
- Envio de mensagens via API REST do Telegram (requests puro, sem biblioteca
  externa)
- Polling de comandos via long polling direto na API do Telegram
- Formatadores independentes para cada protocolo: format_top5, format_cascade,
  format_spark, format_confirm
- Loop Top5: intervalo de 30 min, configuravel via SCAN_INTERVAL_TOP5 no .env
- Loop Cascade: intervalo de 30 min, configuravel via SCAN_INTERVAL_CASCADE no
  .env
- Loop Spark: intervalo de 15 min, configuravel via SCAN_INTERVAL_SPARK no .env
- Quatro threads independentes: top5, cascade, spark, polling
- Horario automatico: seg-sex 06:00-23:59, dom 20:00-23:59, sab somente sob
  demanda
- Cooldown por ativo: 15 min entre notificacoes do mesmo simbolo
- Estado de cooldown em memoria com threading.Lock para acesso seguro entre
  threads
- Mensagens antigas descartadas na inicializacao do polling

### Comandos Telegram implementados

- "Claudinho roda os protocolos": disparo unico dos tres scanners, ignora
  horario e cooldown
- "Claudinho mute": silencia notificacoes, loops continuam rodando
- "Claudinho unmute": retoma notificacoes
- "confirm SYMBOL": analise pontual via confirm.py, responde no chat

### Dependencias adicionadas

- pytz: timezone America/Sao_Paulo para controle de horario de operacao
- python-telegram-bot removido do requirements (nao utilizado)

### Decisoes de arquitetura

- Ver DECISION_LOG.md

---

## [0.2.0] - 2026-03-18

### Adicionado

- src/cascade_market_reader.py: versao revisada do scanner Cascade (renomeado de
  market_reader.py)
- src/spark_market_reader.py: scanner do protocolo Spark
- src/spark_universe.py: mapeamento e pre-selecao do universo de ativos do Spark

### Protocolo Cascade (v2)

- 1h reformulado como veto puro: rejeita apenas se MA7 abaixo de MA99 ou MACD
  claramente negativo
- Gatilho do 5m reformulado: MACD ascendente em direcao ao zero ou acima
  (captura entrada antes do cruzamento)
- Sweet spot: MACD pre-cruzamento com StochRSI e TSI ja subindo — recovery
  minimo de 30% do minimo recente
- BB inclinadas para cima (ambas as bandas, janela de 5 velas) adicionada como
  condicao no 5m e 15m
- Correlacao BTC via Pearson (janela 20 velas) no 5m e 15m: aceita aligned
  (>0.6) ou independent (<0.4)
- Dead zone BTC alargada: 0.4 a 0.6 (antes 0.3 a 0.7)
- StochRSI no 15m: limite de 80 dispensado quando 1h tem MA alinhada
- Modo DEBUG adicionado: exibe motivo de rejeicao por ativo e por filtro
- Aviso de SL acima de 8% no output do setup

### Protocolo Spark (v1)

- Universo: 250 a 400 ativos esquecidos com volume entre $1M e $50M e variacao
  24h entre -8% e +8%
- Fase 1 - Compressao: BBW no bottom 25% do historico proprio do ativo no 1h e
  15m
- Fase 2 - Pre-sinal: corpo medio, fechando pra cima, volume crescendo, preco
  encostando na banda superior no 5m
- Fase 3 - Gatilho PAH: volume 3x acima da media, corpo cheio, rompimento da
  banda superior no 1m
- Candidatos identificados: ativos comprimidos com pre-sinal mas sem gatilho
  ainda
- Callback Spark: 3% se spread BB menor que 5%, 5% se maior

### Decisoes de arquitetura

- Ver DECISION_LOG.md

---

## [0.1.0] - 2026-03-17

### Adicionado

- README.md com descricao do projeto, fases de desenvolvimento e regras de risco
- .gitignore cobrindo credenciais, venv, cache Python e IDEs
- .env.example com template de variaveis de ambiente
- requirements.txt com dependencias da Fase 1
- config.py com parametros centrais de todos os protocolos e regras de banca
- src/market_reader.py: scanner completo do protocolo Cascade (v1)

### Protocolo Cascade (v1)

- Scanner dinamico: top 30 e bottom 30 simbolos USDT por variacao 24h
- Filtro de liquidez: volume minimo de $10M USD nas 24h
- Analise em cascata: 1h (macro) -> 15m (confirmacao) -> 5m (entrada)
- Indicadores implementados: MA7/25/99, Bollinger Bands, MACD, StochRSI, TSI,
  Volume
- Gestao de risco dinamica via spread Bollinger no 5m:
  - Spread < 5%: SL = banda inferior BB | Callback = 1%
  - Spread >= 5%: SL = banda inferior BB | Callback = 2%
- Output estruturado no terminal com entrada, SL, callback e checklist de
  confirmacoes

### Decisoes de arquitetura

- Ver DECISION_LOG.md
