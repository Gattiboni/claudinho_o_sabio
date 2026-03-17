# config.py
# Parametros centrais do claudinho_o_sabio
# Alterar com criterio. Estes valores refletem os protocolos validados pelo operador.

# -----------------------------------------------------------------------
# BANCA E RISCO
# -----------------------------------------------------------------------

BANCA_USD = 100.0                  # Capital total da sub-carteira
MARGEM_MAX_PCT = 0.08              # Exposicao maxima em margem (8% default, range 7-10%)
VALOR_MAX_POR_POSICAO_USD = 50.0   # Teto absoluto por posicao (protocolo GEM)

# -----------------------------------------------------------------------
# TIMEFRAMES MONITORADOS
# -----------------------------------------------------------------------

TIMEFRAMES = ["5m", "15m", "1h"]
TIMEFRAME_PRINCIPAL = "5m"
TIMEFRAME_CONFIRMACAO = ["15m", "1h"]

# -----------------------------------------------------------------------
# ATIVOS MONITORADOS
# Foco inicial em altcoins com liquidez relevante (volume 24h > 10M USD)
# -----------------------------------------------------------------------

SYMBOLS = [
    "SOLUSDT",
    "AVAXUSDT",
    "DOTUSDT",
    "LINKUSDT",
    "MATICUSDT",
    "ARBUSDT",
    "OPUSDT",
    "INJUSDT",
]

# -----------------------------------------------------------------------
# INDICADORES - PARAMETROS
# -----------------------------------------------------------------------

# Medias Moveis
MA_PERIODS = [7, 25, 99]

# Bollinger Bands
BB_PERIOD = 20
BB_STD = 2.0
BB_SPREAD_MIN_PCT = 0.06           # Spread minimo de 6% para PBS

# MACD
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# Stochastic RSI
STOCH_RSI_PERIOD = 14
STOCH_RSI_SMOOTH_K = 3
STOCH_RSI_SMOOTH_D = 3

# TLI (True Strength Index) - aproximado via TSI
TSI_FAST = 13
TSI_SLOW = 25

# Volume minimo 24h (USD) para validar liquidez - protocolo SIA
VOLUME_MIN_24H_USD = 10_000_000

# -----------------------------------------------------------------------
# PROTOCOLO GEM - Guarded Exposure Model
# -----------------------------------------------------------------------

GEM = {
    "sl_pct": 0.025,               # Stop loss: 2.5% abaixo da entrada (range 2-3%)
    "trailing_trigger_pct": 0.02,  # Trailing ativa apos +2% sobre entrada
    "trailing_callback_pct": 0.02, # Callback do trailing: 2%
    "valor_por_posicao_usd": 50.0, # Exposicao maxima por posicao
}

# -----------------------------------------------------------------------
# PROTOCOLO BVE - Bird View Entry
# -----------------------------------------------------------------------

BVE = {
    "sl_max_pct": 0.03,            # SL tecnico deve caber em -3% no 5min
    "trailing_1_trigger_pct": 0.02,# Guarda-chuva: ativa em +2%
    "trailing_1_callback_pct": 0.02,
    "trailing_2_trigger_pct": 0.03,# Gaviao Real: ativa em +3%
    "trailing_2_callback_pct": 0.01,
    "margem_max_pct": 0.15,        # Margem total <= 15% da banca
}

# -----------------------------------------------------------------------
# PROTOCOLO PBS - Precision Breakout Scalping
# -----------------------------------------------------------------------

PBS = {
    "sl_pct_min": 0.005,           # Hard stop minimo: 0.5% abaixo da entrada
    "sl_pct_max": 0.010,           # Hard stop maximo: 1.0%
    "trailing_trigger_pct": 0.005, # Trailing ativa em +0.5%
    "trailing_callback_pct": 0.010,# Callback: 1.0%
    "bb_spread_min_pct": 0.06,     # Bollinger spread minimo: 6%
}

# -----------------------------------------------------------------------
# PROTOCOLO CURIOUS GEM
# -----------------------------------------------------------------------

CURIOUS_GEM = {
    "tp1_pct": 0.03,               # TP1: +3% (realiza 50% da posicao)
    "trailing_1_trigger_offset_pct": 0.003,  # Guardiao: TP1 + 0.3%
    "trailing_1_callback_pct": 0.02,
    "trailing_1_qty_pct": 0.25,    # 25% da posicao original
    "trailing_2_trigger_pct_min": 0.06,      # Explorador: +6% a +8%
    "trailing_2_trigger_pct_max": 0.08,
    "trailing_2_callback_pct": 0.015,
    "trailing_2_qty_pct": 0.25,
}

# -----------------------------------------------------------------------
# PROTOCOLO HOUDINI STRATEGIC SCATTER
# -----------------------------------------------------------------------

HOUDINI = {
    "variacao_24h_min_pct": 0.03,  # Filtro: altcoins entre +3% e +5% nas 24h
    "variacao_24h_max_pct": 0.05,
    "sl_max_pct": 0.03,            # Descarta ativo se SL tecnico > 3%
    "trailing_trigger_pct_min": 0.03,
    "trailing_trigger_pct_max": 0.05,
    "trailing_callback_pct": 0.015,
    "valor_por_ativo_usd": 20.0,
    "max_posicoes_simultaneas": 8,
    "margem_max_pct": 0.15,
}

# -----------------------------------------------------------------------
# PROTOCOLO SCOUT IN ACTION (SIA)
# -----------------------------------------------------------------------

SIA = {
    "valor_entrada_usd": 6.0,
    "reducao_imediata_usd": 5.0,   # Encerra $5 logo apos abertura
    "alavancagem": 20,
    "roi_decisao_pct": 0.20,       # A partir de 20-30% ROI, avaliar gestao
    "roi_expansao_pct": 0.30,      # Acima de 30%, expandir analise
}

# -----------------------------------------------------------------------
# PROTOCOLO TOD - Trailing Overweight Defense
# -----------------------------------------------------------------------

TOD = {
    "tp1_qty_pct": 0.75,           # Realiza 75% da posicao no TP1
    "tp1_targets_pct": [0.01, 0.015, 0.025],  # 1%, 1.5% ou 2.5% conforme volatilidade
    "trailing_callback_pct": 0.03, # Trailing no restante: callback 3%
}

# -----------------------------------------------------------------------
# API BINANCE FUTURES (publica - Fase 1)
# -----------------------------------------------------------------------

BINANCE_BASE_URL = "https://fapi.binance.com"
BINANCE_KLINES_ENDPOINT = "/fapi/v1/klines"
CANDLES_LIMIT = 100                # Quantidade de candles por requisicao
