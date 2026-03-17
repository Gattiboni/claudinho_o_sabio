# claudinho_o_sabio

> "Entro com visao. Protejo com honra. Cresco sem controle."

Agente autonomo de analise e execucao de futuros na Binance, baseado nos
protocolos proprietarios de trading de Gattiboni Enterprises. Desenvolvido com
Claude (Anthropic) como motor de decisao.

---

## Objetivo

Substituir a presenca humana constante no mercado sem substituir o julgamento
humano nos momentos que importam. O agente:

1. Le o mercado continuamente (candles, indicadores, volume)
2. Identifica setups validos conforme os protocolos documentados
3. Notifica o operador via Telegram com analise estruturada
4. Executa ordens com gestao de risco automatica (fases futuras)

---

## Protocolos Implementados

| Protocolo                         | Descricao                                       | Status    |
| --------------------------------- | ----------------------------------------------- | --------- |
| GEM - Guarded Exposure Model      | Entrada em assimetria com Bollinger estreitando | Fase 1    |
| BVE - Bird View Entry             | Trailing duplo sem TP fixo                      | Planejado |
| PBS - Precision Breakout Scalping | Rompimento de topo de Bollinger com corpo cheio | Planejado |
| Curious GEM                       | Gestao pos-TP1 com trailing independente        | Planejado |
| Houdini Strategic Scatter         | Matriz de altcoins fora do radar                | Planejado |
| Scout In Action (SIA)             | Sondagem de ativos com entrada minima           | Planejado |
| TOD - Trailing Overweight Defense | Protecao de ganhos com trailing 3%              | Planejado |

---

## Arquitetura do Projeto

```
claudinho_o_sabio/
├── README.md               <- este arquivo
├── .env                    <- credenciais (NUNCA versionar)
├── .env.example            <- template de variaveis sem valores reais
├── .gitignore
├── requirements.txt        <- dependencias Python
├── config.py               <- parametros dos protocolos e da banca
└── src/
    ├── market_reader.py    <- leitura de candles e calculo de indicadores
    ├── protocol_engine.py  <- logica de decisao dos protocolos (fase 2)
    ├── notifier.py         <- envio de alertas via Telegram (fase 2)
    └── executor.py         <- execucao de ordens na Binance (fase 3)
```

---

## Fases de Desenvolvimento

### Fase 1 - Olhos (leitura, sem dinheiro)

- Conexao com API publica da Binance Futures (fapi.binance.com)
- Leitura de candles nos timeframes 5min, 15min, 1h
- Calculo de: MACD, Stoch RSI, Bollinger Bands, TLI, Volume, MAs (7, 25, 99)
- Output em terminal: setup identificado ou ausencia de setup

### Fase 2 - Voz (notificacao, sem execucao)

- Deteccao automatica de condicoes de entrada por protocolo
- Envio de alerta via Telegram com: ativo, timeframe, protocolo ativado, SL
  sugerido, contexto de risco
- Pipeline de analise de trades exportados da Binance

### Fase 3 - Maos (execucao supervisionada)

- Execucao de ordens via API autenticada da Binance Futures
- Gestao automatica de SL e trailing conforme protocolo ativo
- Sub-carteira isolada com banca inicial: $100 USD
- Margem maxima exposta: 7 a 10% da banca

### Fase 4 - Cerebro (autonomia total)

- Operacao sem aprovacao humana dentro dos limites de risco definidos
- Re-avaliacao e relatorio diario de performance

---

## Regras de Risco (Inegociaveis)

```
Banca inicial:          $100 USD (sub-carteira isolada)
Margem maxima exposta:  7% a 10% da banca
Prioridade:             1. Proteger a banca
                        2. Salvar o investimento
                        3. Lucrar
Meta de performance:    5% a 7% ao dia (quando condicoes ideais)
```

---

## Stack Tecnica

| Componente       | Tecnologia                                                  |
| ---------------- | ----------------------------------------------------------- |
| Linguagem        | Python 3.11+                                                |
| API de Mercado   | Binance Futures REST (fapi.binance.com) - publica na Fase 1 |
| Indicadores      | pandas-ta                                                   |
| Notificacoes     | Telegram Bot API                                            |
| Deploy           | Railway                                                     |
| Banco de dados   | Supabase (fases futuras)                                    |
| Motor de decisao | Claude API (Anthropic)                                      |

---

## Setup Local (Fase 1)

```bash
# 1. Clonar o repositorio
git clone https://github.com/Gattiboni/claudinho_o_sabio.git
cd claudinho_o_sabio

# 2. Criar ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variaveis de ambiente
cp .env.example .env
# editar .env com suas credenciais

# 5. Rodar o leitor de mercado
python src/market_reader.py
```

---

## Variaveis de Ambiente

```env
# Binance (necessario apenas na Fase 3)
BINANCE_API_KEY=
BINANCE_API_SECRET=

# Telegram (Fase 2)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Anthropic - motor de decisao (Fase 2+)
ANTHROPIC_API_KEY=
```

---

## Fonte de Dados

- REST publico (Fase 1): https://fapi.binance.com/fapi/v1/klines
- Documentacao oficial:
  https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info
- Conector Python oficial:
  https://github.com/binance/binance-futures-connector-python

---

## Disclaimer

Este projeto e de uso pessoal e experimental. Nao e recomendacao de
investimento. Trading de futuros com alavancagem envolve risco de perda total do
capital. Os protocolos aqui implementados foram desenvolvidos e validados pelo
operador ao longo de sua experiencia pessoal.

---

Gattiboni Enterprises - claudinho_o_sabio v0.1
