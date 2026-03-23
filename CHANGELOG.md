# CHANGELOG

Todas as mudancas relevantes do projeto serao documentadas aqui. Formato baseado
em Keep a Changelog (https://keepachangelog.com).

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
