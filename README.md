# MotoGP Data Lab

Uma plataforma de análise do campeonato que coleta resultados históricos, compara pilotos e equipes, identifica padrões e tenta prever o desempenho nas próximas corridas.

**Big Data · MongoDB · Séries temporais · Estatística · Machine learning**

## Objetivos

- Construir um pipeline de coleta e armazenamento de dados históricos da MotoGP.
- Analisar o desempenho de pilotos e equipes em diferentes sessões e circuitos.
- Identificar padrões, consistência e relações entre qualificação e resultado final.
- Desenvolver modelos estatísticos e de machine learning para estimar pontos ou posições.
- Aplicar conceitos de engenharia de dados, análise de dados e sistemas distribuídos.

### Perguntas de pesquisa

- Qual piloto é mais consistente, independentemente das vitórias?
- Quanto a posição na qualificação influencia o resultado?
- Quais pilotos têm melhor desempenho em determinados circuitos?
- É possível prever pontos ou posições usando os resultados anteriores?

## Tecnologias

| Tecnologia | Utilização |
|---|---|
| Python | Coleta, transformação e análise dos dados |
| REST API + `requests` | Obtenção dos dados históricos |
| MongoDB | Armazenamento dos documentos coletados |
| Docker + Docker Compose | Execução e gerenciamento do MongoDB |
| `pymongo` | Comunicação entre Python e MongoDB |
| Pandas | Limpeza, transformação e análise tabular |
| Jupyter Notebook | Análise exploratória e experimentos |
| Matplotlib / Seaborn | Visualização dos resultados |
| Scikit-learn | Modelos preditivos e avaliação |
| Git + GitHub | Versionamento, documentação e reprodutibilidade |

### Fonte de dados

A coleta inicial utiliza a API comunitária documentada do MotoGP PulseLive:

- **Base URL:** `https://api.motogp.pulselive.com/motogp/v1`
- **Documentação comunitária:** [MotoGP-API — GitHub](https://github.com/robschmitt/MotoGP-API)

Endpoints utilizados:

- `GET /results/seasons` — temporadas disponíveis.
- `GET /results/events?seasonUuid={season_id}` — eventos de uma temporada.
- `GET /results/categories?seasonUuid={season_id}` — categorias.
- `GET /results/sessions?eventUuid={event_id}&categoryUuid={category_id}` — sessões de um evento e categoria.
- `GET /results/session/{session_id}/classification?seasonYear={year}&test=false` — classificação de uma sessão.

> **Nota:** trata-se de uma API comunitariamente documentada, não de um contrato público oficial garantido. Os endpoints e formatos podem mudar. A coleta deve respeitar as condições de acesso e evitar requisições excessivas.

## Arquitetura

```text
MotoGP PulseLive API
        |
        v
 Python — requests
        |
        v
 Ingestão e validação
        |
        v
 MongoDB — Docker
        |
        v
 Pandas / Jupyter
        |
        v
 Estatística e visualização
        |
        v
 Machine learning
```

## Estrutura do projeto

```text
motogp-data-lab/
├── docker-compose.yaml
├── docker/
│   └── python.Dockerfile
├── .env.example
├── .dockerignore
├── .gitignore
├── requirements.txt
├── requirements-dev.txt
├── pytest.ini
├── README.md
├── src/
│   ├── __init__.py
│   └── motogp_data_lab/
│       ├── __init__.py
│       ├── config.py
│       ├── api_client.py
│       ├── storage.py
│       ├── ingestion.py
│       ├── validation.py
│       └── main.py
├── tests/
│   └── test_api_client.py
├── test_api.py
├── test_storage.py
├── notebooks/        (planejado)
└── docs/             (planejado)
```

- `docker-compose.yaml`: serviços `mongodb` (com autenticação e healthcheck) e `ingestion`.
- `docker/python.Dockerfile`: imagem que executa o pipeline de ingestão.
- `.env.example`: modelo das variáveis de ambiente; o `.env` real fica fora do Git.
- `config.py`: lê as variáveis de ambiente (`MONGO_URI`, `MONGO_DB`, `LOG_LEVEL`).
- `api_client.py`: centraliza as requisições HTTP à API, com retry, throttling, logs e uma função por endpoint.
- `storage.py`: gerencia a conexão e as operações no MongoDB.
- `ingestion.py`: coordena a coleta de eventos, sessões e classificações.
- `validation.py`: regras de qualidade dos dados (em desenvolvimento).
- `main.py`: ponto de entrada para executar o pipeline.
- `tests/`: testes automatizados com pytest.
- `test_api.py` e `test_storage.py`: scripts de verificação manual contra a API real e o MongoDB.
- `notebooks/`: análises exploratórias e experimentos estatísticos.
- `docs/`: documentação do modelo de dados (coleções, campos e relacionamentos).

## Plano de desenvolvimento

### 1. Validar a coleta inicial

**Status:** primeira coleta concluída para o GP da Tailândia de 2025.

- Confirmar os documentos nas coleções `events`, `sessions` e `classification`.
- Verificar quantidades, campos ausentes e relacionamentos entre documentos.
- Executar novamente a coleta e confirmar que não são criadas duplicatas.
- Criar um script de validação e registrar os resultados.

**Resultado esperado:** uma coleta reproduzível e dados cuja integridade pode ser verificada.

### 2. Consolidar o modelo de dados

- Documentar o esquema das coleções e os identificadores utilizados.
- Definir índices para consultas frequentes.
- Validar referências entre eventos, sessões e classificações.
- Tratar erros HTTP, timeouts, registros de execução e tentativas de recuperação.

**Resultado esperado:** uma base MongoDB consistente, documentada e preparada para consultas.

### 3. Realizar análise exploratória

- Transformar os documentos em DataFrames com Pandas.
- Limpar e normalizar tempos, posições e valores ausentes.
- Calcular estatísticas de desempenho e consistência.
- Criar gráficos comparativos entre pilotos, sessões e equipes.

**Resultado esperado:** um conjunto de análises documentadas, com conclusões e limitações.

### 4. Expandir a coleta histórica

- Expandir do GP da Tailândia para os demais eventos de 2025.
- Avaliar a inclusão de outras temporadas e categorias.
- Medir o volume de dados, o tempo de execução e a frequência de falhas.
- Garantir que a coleta pode ser retomada sem duplicar os dados já armazenados.

**Resultado esperado:** uma base histórica que permita comparações entre circuitos e temporadas.

### 5. Desenvolver modelos preditivos

- Definir uma variável-alvo, como pontos ou posição final.
- Construir atributos com dados disponíveis antes da corrida.
- Estabelecer uma referência simples para comparação.
- Treinar e avaliar modelos com Scikit-learn.
- Separar treino e teste respeitando a ordem temporal, evitando vazamento de informação.

**Resultado esperado:** experimentos reproduzíveis, com métricas, comparação de modelos e limitações documentadas.

## Ambiente de desenvolvimento

Requisitos: Python 3.12 ou compatível com as dependências, Docker Engine e Docker Compose.

### Preparação

Criar e ativar um ambiente virtual:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Iniciar o MongoDB:

```bash
docker compose up -d
docker compose ps
```

Executar o pipeline:

```bash
python -m src.motogp_data_lab.main
```

Para executar os testes unitários da API:
```bash
pytest -v
```

Para consultar os logs do MongoDB:

```bash
docker compose logs mongodb
```

### Dependências Python

As dependências ficam em dois arquivos, todas com versão fixada:

| Arquivo | Uso | Conteúdo |
|---|---|---|
| `requirements.txt` | Execução do pipeline (inclusive na imagem Docker) | `requests`, `urllib3`, `pymongo`, `python-dotenv` |
| `requirements-dev.txt` | Desenvolvimento local | Inclui o `requirements.txt` (`-r`) e acrescenta `pytest` |

A imagem Docker instala apenas o `requirements.txt`, então as ferramentas de desenvolvimento não entram nela.

Pandas, Jupyter, bibliotecas de visualização e Scikit-learn serão adicionados quando as respectivas etapas forem iniciadas.

## Relação com as disciplinas do mestrado

| Disciplina | Aplicação no projeto |
|---|---|
| Big Data | Ingestão, armazenamento, modelagem e processamento de dados |
| Ciência de Dados / Machine Learning | Estatística, análise exploratória, atributos e modelos preditivos |
| Séries temporais | Evolução do desempenho ao longo das sessões e temporadas |
| Model-Based Development | Modelagem do pipeline, estados, transições e tratamento de falhas |
| Cyber-Physical Systems | Possível extensão com simulação de telemetria e coleta via MQTT |
| NLP | Possível extensão para análise de notícias e comentários sobre corridas |

As extensões de telemetria e NLP são possibilidades futuras, não requisitos para a primeira versão.

## Critérios de evolução

O projeto avança quando cada etapa produz resultados verificáveis:

1. Dados coletados e validados.
2. Armazenamento idempotente e consultas documentadas.
3. Análises exploratórias reproduzíveis.
4. Dataset histórico ampliado e consistente.
5. Modelos preditivos avaliados com métricas adequadas.

**Objetivo final:** transformar resultados históricos da MotoGP em uma base de dados analítica capaz de explicar padrões de desempenho e avaliar, de forma fundamentada, até que ponto é possível prever resultados futuros.
