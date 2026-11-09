# Modelo de dados

Este documento descreve como os dados da API do MotoGP PulseLive estão armazenados no MongoDB: as coleções, os campos, os relacionamentos e as particularidades encontradas.

As informações foram levantadas a partir dos documentos reais do banco (`findOne` e agregações sobre todos os documentos), não da documentação da API. A base de referência é a coleta do **GP da Tailândia de 2025, categoria MotoGP**: 1 evento, 8 sessões e 156 documentos de classificação. O que ainda depende de outras temporadas ou categorias está em [Pendências](#pendências).

## Princípios

- **O documento bruto da API é mantido intacto.** A ingestão só acrescenta os [metadados de ingestão](#metadados-de-ingestão) e, quando não existem no documento original, chaves de relacionamento (caso da `classification`). Limpeza, conversão de tipos e achatamento ficam na camada analítica (planejada).
- **Sem duplicação de dados.** Quando um campo já existe aninhado (por exemplo, `sessions.event.id`), ele é consultado e indexado com dot notation, em vez de ser copiado para o nível de cima.
- **Idempotência.** Todo documento usa o `id` da API como `_id`, e a gravação é um upsert (`UpdateOne` com `$set` e `upsert=True`, enviados em lote com `bulk_write`). Executar a coleta de novo atualiza os documentos existentes sem criar duplicatas. Em uma nova execução, `modified_count > 0` indica que a API alterou um dado já coletado: um `$set` com valores idênticos não modifica o documento.

## Visão geral

```text
events  (1 por GP; vale para todas as categorias)
  │  _id = id do evento
  │
  │ 1:N   sessions.event.id
  ▼
sessions  (1 por sessão × categoria)
  │  _id = id da sessão
  │
  │ 1:N   classification.session_id
  ▼
classification  (1 por piloto × sessão)
     _id = id do item de classificação
```

| Coleção | Chave | Referência ao nível de cima | Origem da referência |
|---|---|---|---|
| `events` | `_id` = `id` | — | — |
| `sessions` | `_id` = `id` | `event.id` (aninhado) | API |
| `classification` | `_id` = `id` | `session_id` (e também `event_id`) | Acrescentada pela ingestão |

O relacionamento é por **referência**, e não por embedding: são relações 1:N que crescem a cada evento, consultadas de forma independente, e a API já fornece os IDs.

A categoria é uma dimensão à parte. O **evento não tem categoria**: o mesmo GP vale para MotoGP, Moto2 e Moto3. A categoria aparece a partir das sessões (`sessions.category.id`).

## Metadados de ingestão

Todo documento das coleções brutas (`events`, `sessions`, `classification`) recebe dois campos gravados pelo `storage.upsert_many()`. O prefixo `_` os separa dos campos da API.

| Campo | Tipo | Operador | Descrição |
|---|---|---|---|
| `_ingested_at` | `Date` (UTC) | `$setOnInsert` | Quando o documento foi **criado** no banco. É calculado uma vez por chamada de `upsert_many`, então todos os documentos de um mesmo lote (por exemplo, a classificação de uma sessão) têm o mesmo valor. |
| `_source_endpoint` | string | `$set` | Endpoint da API que originou o documento. |

Valores de `_source_endpoint`:

| Coleção | Valor |
|---|---|
| `events` | `results/events` |
| `sessions` | `results/sessions` |
| `classification` | `results/session/{session_id}/classification` |

O valor da `classification` é o **modelo** do caminho, com `{session_id}` literal: o ID da sessão específica já está no campo `session_id` do documento.

Por que dois operadores diferentes:
- O `_ingested_at` fica no `$setOnInsert` para ser gravado só na criação. Se estivesse no `$set`, mudaria a cada execução, e o `modified_count` passaria a contar todos os documentos, perdendo o sinal de "a API alterou o dado".
- O `_source_endpoint` pode ficar no `$set` porque o valor é constante para a coleção: em reexecuções ele é idêntico ao gravado e não conta como modificação.

Verificado em 03/11/2026, depois de apagar o banco e rodar a coleta duas vezes: 1 evento, 8 sessões e 156 classificações, todos com os dois campos; o `_ingested_at` manteve o horário da primeira execução.

Limitação: os metadados dizem quando o documento **entrou** no banco, mas não quando foi **alterado** pela última vez.

## Coleção `events`

Um documento por Grande Prêmio, vindo de `GET /results/events?seasonUuid={season_id}`.

| Campo | Tipo | Descrição |
|---|---|---|
| `_id`, `id` | string (UUID) | Identificador do evento. São iguais. |
| `name` | string | Nome oficial, ex.: `'GRAND PRIX OF THAILAND'`. |
| `short_name` | string | Sigla, ex.: `'THA'`. **Não é chave**: se repete todos os anos. |
| `sponsored_name` | string | Nome com patrocinador. Pode mudar entre anos. |
| `additional_name` | string | Nome curto, ex.: `'THAILAND'`. |
| `date_start`, `date_end` | string | Datas no formato `'AAAA-MM-DD'`. Não são `Date`. |
| `status` | string | Situação do evento, ex.: `'FINISHED'`. |
| `test` | bool | `true` para testes de pré-temporada. |
| `season` | objeto | `{id, year, current}`. `year` é **int** (`2025`). |
| `circuit` | objeto | `{id, name, legacy_id, place, nation, events_id}`. |
| `country` | objeto | `{iso, name, region_iso}`. |

Campos ignorados na análise: `event_files` (links para PDFs), `legacy_id` (IDs do sistema antigo, um por categoria), `toad_api_uuid`.

Observações:
- **`season.current` é um retrato do momento da coleta.** Uma temporada aparece como `true` enquanto está em andamento e `false` depois. Não deve ser usado na análise.
- Para comparar resultados de um mesmo circuito ao longo dos anos, a chave é `circuit.id`, e não `circuit.name`. A estabilidade desse ID entre temporadas ainda precisa ser conferida.

## Coleção `sessions`

Um documento por sessão de uma categoria, vindo de `GET /results/sessions?eventUuid={event_id}&categoryUuid={category_id}`.

| Campo | Tipo | Descrição |
|---|---|---|
| `_id`, `id` | string (UUID) | Identificador da sessão. São iguais. |
| `type` | string | Tipo da sessão: `FP`, `PR`, `Q`, `SPR`, `WUP`, `RAC`. |
| `number` | int ou null | Número da sessão quando o tipo se repete (`FP` 1 e 2, `Q` 1 e 2); `null` nos demais. |
| `date` | string | Data e hora de início em UTC, ex.: `'2025-03-02T15:00:00+00:00'`. Não é `Date`. |
| `status` | string | Ex.: `'FINISHED'`. |
| `category` | objeto | `{id, legacy_id, name}`. O `name` vem como `'MotoGP™'` (com o símbolo); comparar sempre pelo `id`. |
| `event` | objeto | Cópia parcial do evento: `{id, name, sponsored_name, short_name, test, season, circuit, country}`. |
| `circuit` | string | Apenas o **nome** do circuito. |
| `condition` | objeto | `{track, air, humidity, ground, weather}`, tudo como string. |

Campos ignorados na análise: `session_files` (links para PDFs, alguns com `url: ''`).

Observações:
- **A referência ao evento é `event.id`**, aninhada. Não existe `event_id` no nível de cima.
- A chave de uma sessão dentro do fim de semana é `type` + `number`, porque `FP` e `Q` se repetem.
- `condition` tem valores com unidade (`air: '36º'`, `humidity: '41%'`); para usar como número, é preciso extrair o valor. `track` (`'Dry'`, `'Wet'`) é útil como atributo para os modelos.

### Sessões de um fim de semana (MotoGP, 2025)

| `type` | `number` | Sessão | Pilotos (MotoGP) | Pontua |
|---|---|---|---|---|
| `FP` | 1 | Free Practice 1 | 22 | Não |
| `PR` | null | Practice | 22 | Não |
| `FP` | 2 | Free Practice 2 | 22 | Não |
| `Q` | 1 | Qualifying 1 | 12 | Não |
| `Q` | 2 | Qualifying 2 | 12 | Não |
| `SPR` | null | Sprint | 22 | Sim |
| `WUP` | null | Warm Up | 22 | Não |
| `RAC` | null | Corrida principal | 22 | Sim |

O formato depende da categoria e do ano:
- Na MotoGP, os 10 primeiros do `PR` vão direto para o Q2, e os 2 primeiros do Q1 completam o Q2 (12 pilotos). Na Moto2 e na Moto3, são 14 direto mais 4 do Q1 (18 pilotos).
- A Sprint (`SPR`) só existe na MotoGP e só a partir de 2023. Temporadas anteriores têm outro conjunto de sessões.

Por isso, o número de documentos de classificação por sessão não é fixo. Qualquer regra de consistência sobre ele precisa considerar a categoria, o tipo de sessão e o ano.

## Coleção `classification`

Um documento por piloto em cada sessão. Vem da lista `classification` de `GET /results/session/{session_id}/classification`, acrescida de chaves de relacionamento pela ingestão.

### Campos comuns a todas as sessões

| Campo | Tipo | Descrição |
|---|---|---|
| `_id`, `id` | string (UUID) | Identificador do item de classificação. São iguais. |
| `position` | int ou null | Posição final. `null` para pilotos não classificados. |
| `status` | string | `'INSTND'` (classificado) ou `'OUTSTND'` (não classificado). |
| `total_laps` | int | Voltas completadas. |
| `gap` | objeto | Diferenças de tempo como string. O conteúdo varia com o tipo de sessão (ver abaixo). |
| `rider` | objeto | `{id, full_name, country, legacy_id, riders_id, number, riders_api_uuid}`. |
| `team` | objeto | `{id, name, legacy_id, season: {id, year, current}}`. O `team.id` não identifica a equipe (ver [Equipe](#equipe-team)). |
| `constructor` | objeto | `{id, name, legacy_id}`, ex.: `'Ducati'`. |

### Campos acrescentados pela ingestão

| Campo | Tipo | Origem |
|---|---|---|
| `session_id` | string | `id` da sessão consultada. |
| `event_id` | string | `id` do evento da sessão. |
| `season_year` | int | Constante `SEASON_YEAR` do `ingestion.py`. |
| `category_id` | string | Constante `CATEGORY_ID` do `ingestion.py`. |
| `rider_id` | string | Cópia de `rider.id` (ver [IDs do piloto](#ids-do-piloto)). |

`season_year` e `category_id` vêm de **constantes do código**, não da resposta da API. Quando a coleta for parametrizada (Fase 3), eles devem vir da temporada e da categoria efetivamente consultadas.

### Dois formatos de documento

A coleção guarda documentos de formatos diferentes, conforme o tipo de sessão (padrão **Polymorphic**). O campo que diferencia é o `type` da sessão de origem.

| | Sessões cronometradas (`FP`, `PR`, `Q`, `WUP`) | Corridas (`SPR`, `RAC`) |
|---|---|---|
| Tempo | `best_lap: {number, time}`: volta mais rápida e em qual volta ela ocorreu | `time`: tempo total de prova |
| Velocidade | `top_speed`: velocidade máxima (km/h) | `average_speed`: velocidade média (km/h) |
| `gap` | `{first, prev}`: diferença para o primeiro e para o anterior | `{first, lap}`: diferença para o primeiro e voltas atrás |
| `points` | ausente | int |

Formatos de tempo (todos string): `best_lap.time` `'01:29.423'`, `time` `'39:37.244'` (minutos:segundos.milésimos), `gap.first` `'0.000'` (segundos).

### Pontos

A classificação de `SPR` e `RAC` traz o campo `points`, ao contrário do que diz a documentação comunitária da API. Na Tailândia 2025, as somas foram 140 na corrida (25 + 20 + 16 + … + 1) e 49 na Sprint (12 + 9 + 7 + … + 1), batendo exatamente com a tabela oficial de pontos.

O `points` da API é a fonte. A tabela posição × pontos serve como regra de validação.

### Pilotos não classificados (`OUTSTND`)

| Campo | Valor | Interpretação |
|---|---|---|
| `position` | `null` | Sem posição final. |
| `points` | `0` | Nas corridas. |
| `gap.first` | `'0.000'` | **Não significa empate com o líder.** O valor não é informado. |
| `gap.lap` | ex.: `'4'` | Voltas atrás do vencedor (nas corridas). |
| `time` | ex.: `'34:16.402'` | Tempo até o abandono. |
| `total_laps` | ex.: `22` | Voltas completadas antes de parar. |

O status não informa o motivo (queda, quebra, desclassificação, não largou). Um piloto com `total_laps: 0` e `best_lap.time: ''` nem chegou a rodar (caso observado no `PR`).

### IDs do piloto

O subdocumento `rider` traz dois UUIDs diferentes (em todos os 156 documentos):

| Campo | Exemplo (Marc Márquez) | O que é |
|---|---|---|
| `rider.id` | `f55b433d-38b8-4d1d-bb3a-a709c82a0260` | ID da Results API. Estável entre temporadas. |
| `rider.riders_id` = `rider.riders_api_uuid` | `23e50438-a657-4fb0-a190-3262b5472f29` | ID do piloto na **Broadcast API** (`/riders`, `/teams`). Os dois campos sempre têm o mesmo valor. |
| `rider.legacy_id` | `7444` | ID numérico do sistema antigo; o mesmo nas duas APIs. |
| `rider.number` | `93` | Número de corrida. **Não serve como identificador:** muda entre temporadas (Bagnaia: 1 em 2024, 63 em 2025; Martín: 89 em 2024, 1 em 2025) e vem `null` em 2004. |

Conferido na API em 29/10/2026: o `/riders` devolve o Márquez com `id: '23e50438...'` e `legacy_id: 7444`, e o `/teams` devolve o Bagnaia com o mesmo `id` em 2024 e em 2025.

Conferido em 03/11/2026 no `/results/standings` da MotoGP (1 requisição por temporada):
- **2024 × 2025:** Martín, Bagnaia e Márquez têm o mesmo `rider.id`, o mesmo `riders_api_uuid` e o mesmo `legacy_id` nas duas temporadas.
- **2004:** os 29 pilotos do campeonato têm `rider.id` e `riders_api_uuid` preenchidos (inclusive pilotos já aposentados, como Rossi), e `riders_id` = `riders_api_uuid` em todos.

**Decisão: a chave do piloto é o `rider.id`.** O `rider_id` acrescentado pela ingestão continua sendo uma cópia dele. Motivos: é nativo da Results API, de onde vêm todos os resultados; é estável entre temporadas; e está presente de 2004 a 2025. O `rider.riders_api_uuid`, que já fica guardado no documento bruto, é usado só para ligar a classificação às coleções `riders` e `teams` da Broadcast API.

### Equipe (`team`)

**O `team.id` da Results API não identifica a equipe.** Ele muda a cada temporada e é diferente para cada piloto da mesma equipe:

| Temporada | Piloto | `team.name` | `team.id` | `team.legacy_id` |
|---|---|---|---|---|
| 2024 | Bagnaia | Ducati Lenovo Team | `805737ce...` | 57 |
| 2025 | Bagnaia | Ducati Lenovo Team | `c069c64a...` | 19 |
| 2025 | Márquez | Ducati Lenovo Team | `4728a8ee...` | 24 |

O padrão aparece tanto no `/results/standings` quanto na classificação do GP da Tailândia de 2025 que está no banco. A interpretação mais provável é que o `team` represente a **inscrição do piloto na equipe naquela temporada**, e não a equipe.

Consequências:
- Agrupar por `team.id` separa companheiros de equipe. Por enquanto, a forma de agrupar é `team.name` + ano. Como os nomes mudam com o patrocínio, a análise histórica por equipe vai exigir uma tabela de correspondência.
- **Em 2004, `team` vem `null`** para os 29 pilotos do standings. Falta conferir se a classificação das sessões antigas também vem sem equipe. O `constructor` (fabricante) está presente em 2004 e é a alternativa para atributos que precisam cobrir as temporadas antigas.

## Inconsistências entre coleções

| Dado | `events` | `sessions` | `classification` |
|---|---|---|---|
| Ano da temporada | `season.year`: int `2025` | `event.season`: **string** `'2025'` | `season_year`: int `2025`; `team.season.year`: int |
| Circuito | `circuit`: objeto | `circuit`: string (nome); `event.circuit`: objeto | — |
| Datas | `date_start`/`date_end`: string `'AAAA-MM-DD'` | `date`: string ISO com fuso | — |

Comparar `2025` com `'2025'` não gera erro no MongoDB: a consulta ou o `$lookup` simplesmente não encontra nada. Filtros por ano devem usar sempre o tipo de cada coleção, ou o valor convertido na camada analítica.

Números de velocidade (`top_speed`, `average_speed`) às vezes vêm como `int` (valor redondo) e às vezes como `double`. Em validação com `$jsonSchema`, o tipo correto é `bsonType: "number"`.

## Padrões de modelagem observados

- **Extended Reference:** a sessão guarda o `event.id` junto com uma cópia dos campos mais usados do evento (nome, circuito, país). Isso evita um `$lookup` para exibir a sessão, ao custo de duplicar dados que mudam pouco. Essa duplicação vem da API e é mantida no bruto.
- **Polymorphic:** a `classification` guarda documentos de sessões cronometradas e de corridas, com campos diferentes, na mesma coleção.

## Índices

Além do índice padrão em `_id`, `storage.ensure_indexes()` cria os índices abaixo a cada execução (`create_index` é idempotente). Com eles, o `explain("executionStats")` das consultas passou de `COLLSCAN` para `IXSCAN`.

| Coleção | Índice | Consulta atendida |
|---|---|---|
| `sessions` | `{"event.id": 1}` | Sessões de um evento |
| `classification` | `{session_id: 1}` | Classificação de uma sessão |
| `classification` | `{rider_id: 1, season_year: 1}` | Resultados de um piloto numa temporada |

O índice de `sessions` usa dot notation sobre o campo aninhado, sem copiar o ID para o nível de cima.

## Coleções planejadas

Ainda não implementadas; descritas no plano de ação.

| Coleção | Camada | Conteúdo |
|---|---|---|
| `grid` | Bruta | Posição de largada por piloto (`/results/event/{event_id}/category/{category_id}/grid`) |
| `standings` | Bruta | Classificação do campeonato (`/results/standings`) |
| `riders` | Bruta (dimensão) | Perfil do piloto: nascimento, início de carreira, país e `career` (equipe e número por temporada) (Broadcast API, `/riders/{id}`) |
| `teams` | Bruta (dimensão) | Equipes e elencos por temporada e categoria (Broadcast API, `/teams?categoryUuid=&seasonYear=`) |
| `results` | Analítica | Uma linha por piloto × sessão, com campos achatados e tipados (tempos em segundos, datas como `Date`) |
| `ingestion_runs` | Controle | Início, fim, status, contagens e erros de cada execução |

### Results API × Broadcast API

`riders` e `teams` vêm de outra API do mesmo domínio (a "Broadcast API"), que usa **outros IDs** para as mesmas entidades:

| Entidade | Results API | Broadcast API | Como ligar |
|---|---|---|---|
| Categoria MotoGP | `e8c110ad-64aa-4e8e-8a86-f2f152f6a942` (o mesmo em 2004, 2024 e 2025) | `737ab122-76e1-4081-bedb-334caaa18c70` | `legacy_id` (3 nas duas) |
| Equipe Ducati Lenovo | Um `team.id` por piloto e por temporada (2025: `4728a8ee...`/legacy 24 para Márquez, `c069c64a...`/legacy 19 para Bagnaia) | `892fff2f-7402-4fbd-99fb-5fd567d8a80c` (legacy 15, o mesmo em 2024 e 2025) | Nem o `legacy_id` coincide; a definir |
| Piloto | `rider.id` | `id` = `rider.riders_api_uuid` da classificação | `riders_api_uuid` |
| Temporada | Um UUID por ano (2004: `6c0e0734...`, 2024: `dd12382e...`, 2025: `ae6c6f0d...`) | — | — |
| Evento | `id` | — | `toad_api_uuid` do evento aponta para o evento na Broadcast API |

Cuidados com a Broadcast API:
- O `/riders` traz só a temporada **atual**. Para anos anteriores, os pilotos vêm do `/teams`, que também lista pilotos de teste e substitutos (em 2025, a Ducati Lenovo tem 4).
- O `current_career_step` do piloto (no `/riders`) é a equipe **de hoje**, não a da época da corrida. A equipe de cada corrida vem de `classification.team`. Já o `/riders/{id}` traz `career`, uma lista com uma entrada por temporada (`season`, `number`, `sponsored_team`, `team`, `category`, `type`, `current`), que dá a equipe de cada ano. Dentro do `career`, o `current` é volátil como o `season.current` dos eventos.
- A lista de inscritos de um evento (`/event/{id}/entry`, citada na documentação comunitária) não está disponível: o caminho documentado devolve 400 e a variante com `/results` é bloqueada pelo firewall da API (424 "WAF block detected"), conferido em 29/10/2026.
- As estatísticas de carreira (`/riders/{legacy_id}/statistics`) são agregados atuais e não servem como atributo de previsão (vazamento).

## Pendências

A confirmar ao coletar outras temporadas e categorias:

- **ID do piloto:** resolvida em 03/11/2026 (ver [IDs do piloto](#ids-do-piloto)). A chave é o `rider.id`.
- **Equipe:** o `team.id` da Results API não identifica a equipe (ver [Equipe](#equipe-team)). Falta definir como identificar uma equipe ao longo dos anos, como ligar as equipes das duas APIs e se a classificação das sessões antigas também vem com `team: null`.
- **Campos nulos por época no standings:** em 2024, `sprint_wins`, `sprint_podiums` e `sprint_last_positions` vêm `null` para todos os pilotos, apesar de ter havido sprints. Em 2004, `team`, `rider.number`, `race_wins`, `podiums` e `last_positions` vêm `null`. Não usar esses campos como atributo sem conferir a cobertura por temporada.
- **ID do circuito:** conferir se `circuit.id` é o mesmo em anos diferentes.
- **Pontos em temporadas antigas:** o standings traz `points` em 2004 e 2024 (Rossi, 2004: 304, que confere com o resultado oficial). Falta conferir se a classificação das **sessões** também traz `points` antes de 2025.
- **Sessões em temporadas antigas e em Moto2/Moto3:** conferir os valores reais de `type` e `number`.
- **Outros valores de `status`:** até agora só apareceram `INSTND` e `OUTSTND`.
