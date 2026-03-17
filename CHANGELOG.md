# CHANGELOG

Todas as mudancas relevantes do projeto serao documentadas aqui.
Formato baseado em Keep a Changelog (https://keepachangelog.com).

---

## [0.1.0] - 2026-03-17

### Adicionado

- README.md com descricao do projeto, fases de desenvolvimento e regras de risco
- .gitignore cobrindo credenciais, venv, cache Python e IDEs
- .env.example com template de variaveis de ambiente
- requirements.txt com dependencias da Fase 1
- config.py com parametros centrais de todos os protocolos e regras de banca
- src/market_reader.py: scanner completo do protocolo Cascade

### Protocolo Cascade (v1)

- Scanner dinamico: top 30 e bottom 30 simbolos USDT por variacao 24h
- Filtro de liquidez: volume minimo de $10M USD nas 24h
- Analise em cascata: 1h (macro) -> 15m (confirmacao) -> 5m (entrada)
- Indicadores implementados: MA7/25/99, Bollinger Bands, MACD, StochRSI, TSI, Volume
- Gestao de risco dinamica via spread Bollinger no 5min:
  - Spread < 5%: SL = banda inferior BB, callback = 1%
  - Spread >= 5%: SL = banda inferior BB, callback = 2%
- Output estruturado no terminal com entrada, SL, callback e checklist de confirmacoes

### Decisoes de arquitetura

- Ver DECISION_LOG.md
