# Modelo de dados

Este documento descreve como os dados da API do MotoGP PulseLive estão armazenados no MongoDB: as coleções, os campos, os relacionamentos e as particularidades encontradas.

As informações foram levantadas a partir dos documentos reais do banco (`findOne` e agregações sobre todos os documentos), não da documentação da API. A base de referência é a coleta do **GP da Tailândia de 2025, categoria MotoGP**: 1 evento, 8 sessões e 156 documentos de classificação. O que ainda depende de outras temporadas ou categorias está em [Pendências](#pendências).

## Princípios

- **O documento bruto da API é mantido intacto.** A ingestão só acrescenta os [metadados de ingestão](#metadados-de-ingestão) e, quando não existem no documento original, chaves de relacionamento (caso da `classification`). Limpeza, conversão de tipos e achatamento ficam na camada analítica (planejada).
- **Sem duplicação de dados.** Quando um campo já existe aninhado (por exemplo, `sessions.event.id`), ele é consultado e indexado com dot notation, em vez de ser copiado para o nível de cima.
- **Idempotência.** Todo documento usa o `id` da API como `_id` (as exceções são o `grid`, que não tem `id` na API, e o `teams`, cujo `id` se repete entre temporadas; os dois recebem uma chave composta), e a gravação é um upsert (`UpdateOne` com `$set` e `upsert=True`, enviados em lote com `bulk_write`). Executar a coleta de novo atualiza os documentos existentes sem criar duplicatas. Em uma nova execução, `modified_count > 0` indica que a API alterou um dado já coletado: um `$set` com valores idênticos não modifica o documento.

## Visão geral

```text
events  (1 por GP; vale para todas as categorias)
  │  _id = id do evento
  │
  ├── 1:N   grid.event_id
  │         grid  (1 por piloto × evento × categoria)
  │            _id = "event_id:category_id:rider_id"
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

standings  (1 por piloto × temporada × categoria; fora da hierarquia de eventos)
     _id = id do item do standings

Dimensões (Broadcast API):

riders  (1 por piloto; perfil único, com career[] por temporada)
     _id = id do piloto na Broadcast = classification.rider.riders_api_uuid

teams  (1 por equipe × temporada × categoria; com o elenco embutido)
     _id = "season_year:category_id:team_id"
```

| Coleção | Chave | Referência ao nível de cima | Origem da referência |
|---|---|---|---|
| `events` | `_id` = `id` | — | — |
| `sessions` | `_id` = `id` | `event.id` (aninhado) | API |
| `classification` | `_id` = `id` | `session_id` (e também `event_id`) | Acrescentada pela ingestão |
| `grid` | `_id` = `id` **gerado pela ingestão** | `event_id` | Acrescentada pela ingestão |
| `standings` | `_id` = `id` | `season_year` + `category_id` | Acrescentada pela ingestão |
| `riders` | `_id` = `id` (Broadcast) | — (ligado a partir de `classification.rider.riders_api_uuid`) | API |
| `teams` | `_id` = `id` **gerado pela ingestão** | `season_year` + `category_id` | Acrescentada pela ingestão |

O relacionamento é por **referência**, e não por embedding: são relações 1:N que crescem a cada evento, consultadas de forma independente, e a API já fornece os IDs.

A categoria é uma dimensão à parte. O **evento não tem categoria**: o mesmo GP vale para MotoGP, Moto2 e Moto3. A categoria aparece a partir das sessões (`sessions.category.id`).

## Metadados de ingestão

Todo documento das coleções brutas (`events`, `sessions`, `classification`, `grid`, `standings`, `teams`, `riders`) recebe dois campos gravados pelo `storage.upsert_many()`. O prefixo `_` os separa dos campos da API.

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
| `grid` | `results/event/{event_id}/category/{category_id}/grid` |
| `standings` | `results/standings` |
| `teams` | `teams` |
| `riders` | `riders/{rider_id}` |

Os valores da `classification`, do `grid` e do `riders` são o **modelo** do caminho, com os IDs entre chaves literais: os IDs específicos já estão nos campos do documento (`session_id`, `event_id`, `category_id`; no `riders`, o próprio `id`). Os caminhos sem `results/` são da Broadcast API.

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
| `season_year` | int | Ano passado na linha de comando (`--season`). |
| `category_id` | string | UUID da categoria resolvido a partir de `--category` (`resolve_category_id`). |
| `rider_id` | string | Cópia de `rider.id` (ver [IDs do piloto](#ids-do-piloto)). |

`season_year` e `category_id` vêm da **temporada e da categoria consultadas**, não da resposta da API. O mesmo vale para o `grid` e o `standings`.

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

## Coleção `grid`

Um documento por piloto no grid de largada de um evento, em uma categoria. Vem de `GET /results/event/{event_id}/category/{category_id}/grid`, que devolve uma **lista** (sem `dict` em volta). A coleta faz uma requisição por evento.

| Campo | Tipo | Descrição |
|---|---|---|
| `qualifying_position` | int | Posição no grid (1 a N, sem lacunas). |
| `qualifying_time` | string | Melhor tempo na qualificação, ex.: `'01:28.782'`. |
| `rider` | objeto | `{id, full_name, country, legacy_id, riders_id, riders_api_uuid}`. Ao contrário da classificação, **não traz `number`**. |
| `team_name` | string | Só o **nome** da equipe, sem objeto `team` e sem `constructor`. |
| `category` | objeto | `{id, name, legacy_id}`. |
| `event` | objeto | Cópia do evento: `{id, name, sponsored_name, short_name, test, season, circuit, country}`. Como em `sessions`, `event.season` é **string** (`'2025'`). |

### Chave composta

**O item do grid não tem `id` na API.** Como o `upsert_many` usa o `id` como `_id`, a ingestão gera um:

```text
id = "{event_id}:{category_id}:{rider_id}"
```

Um piloto aparece uma única vez no grid de um evento em uma categoria, então a combinação é única (conferido: 22 pilotos distintos em 22 itens na Tailândia 2025). Incluir o `category_id` evita colisão quando Moto2 e Moto3 forem coletadas, já que o evento é compartilhado entre as categorias.

Esse `id` **não é um identificador da API** e não deve ser usado para consultar a API.

### Campos acrescentados pela ingestão

| Campo | Tipo | Origem |
|---|---|---|
| `id` (e `_id`) | string | Chave composta (acima). |
| `event_id` | string | `id` do evento consultado (repete `event.id`, mas fica no nível de cima por ser parte da chave). |
| `season_year` | int | Temporada consultada. |
| `category_id` | string | Categoria consultada (repete `category.id`). |
| `rider_id` | string | Cópia de `rider.id`. |

### Observações

- O grid é do **evento**, não de uma sessão: não tem `session_id`. Ele é coletado mesmo quando a retomada pula todas as sessões do evento.
- MotoGP 2025: 485 documentos em 22 eventos, de 20 a 24 pilotos por evento (substitutos e wildcards). Em todos os eventos, a maior `qualifying_position` é igual ao número de pilotos.
- **O grid não garante que o piloto largou.** Em 2025, há 10 casos de piloto × evento que estão no grid mas não aparecem na classificação da `RAC` daquele evento (provavelmente pilotos que não largaram). O inverso não acontece. Na análise "grid × chegada", esses pilotos precisam ser tratados à parte.
- O nome do campo é `qualifying_position`. Falta conferir se ele já inclui punições de grid (largar algumas posições atrás) ou se é a posição bruta da qualificação.

## Coleção `standings`

Um documento por piloto na classificação do campeonato de uma temporada e categoria. Vem da lista `classification` de `GET /results/standings?seasonUuid={season_id}&categoryUuid={category_id}`, que devolve um `dict` `{file, classification, xmlFile}` (`file` e `xmlFile` são links para PDF/XML e são descartados). A coleta faz **uma requisição por execução**, fora do laço de eventos, mesmo com `--event`.

| Campo | Tipo | Descrição |
|---|---|---|
| `_id`, `id` | string (UUID) | Identificador do item. Veio igual em duas chamadas seguidas. |
| `position` | int | Posição no campeonato. |
| `points` | int | Pontos acumulados (Sprint + corrida). |
| `rider` | objeto | `{id, full_name, country, legacy_id, riders_id, number, riders_api_uuid}`. |
| `team` | objeto | `{id, name, legacy_id, season}`. Mesmo problema do `team.id` da classificação (ver [Equipe](#equipe-team)). |
| `constructor` | objeto | `{id, name, legacy_id}`. |
| `session` | string | Sempre `'RAC'` em 2025. |
| `race_wins`, `podiums` | int | Vitórias e pódios em corridas. |
| `sprint_wins`, `sprint_podiums` | int | Vitórias e pódios em Sprints (`null` em 2024, ver [Pendências](#pendências)). |
| `last_positions`, `sprint_last_positions` | objeto | Posições nos últimos eventos, por sigla (ex.: `{VAL, POR, MAL}`). Vieram todas `null` em 2025. |
| `position_change` | int ou null | Variação de posição em relação à rodada anterior. |

Campos acrescentados pela ingestão: `season_year`, `category_id` e `rider_id` (cópia de `rider.id`). Não há `event_id` nem `session_id`: o standings é da temporada.

### É um retrato, não um histórico

A API devolve só a classificação **no momento da consulta**, e o upsert sobrescreve o documento a cada execução. Por isso:
- Numa temporada finalizada, o standings é o resultado final e não muda mais.
- Numa temporada em andamento, cada execução substitui os valores anteriores. **A evolução rodada a rodada não fica guardada.** Se for necessária, ela pode ser reconstruída somando os `points` da `classification` até cada evento.
- `last_positions` e `position_change` dependem do momento da consulta e **não devem ser usados como atributo** de previsão (vazamento).

### Conferência com a classificação

Em 10/11/2026, na MotoGP 2025: para os 29 pilotos do standings, o `points` é **exatamente igual** à soma dos `points` da `classification` (`SPR` + `RAC`) do mesmo `rider_id`. Marc Márquez 545, Álex Márquez 467, Bezzecchi 353.

## Coleção `teams`

Um documento por equipe em uma temporada e categoria, com o elenco embutido. Vem da **Broadcast API**: `GET /teams?categoryUuid={broadcast_category_id}&seasonYear={ano}`, que devolve uma **lista**. A coleta faz **uma requisição por execução**, fora do laço de eventos.

O `categoryUuid` é o da Broadcast, diferente do da Results. A ingestão o resolve com `resolve_broadcast_category()`, que consulta `GET /categories?seasonYear={ano}` e casa pelo **nome normalizado** (sem `™`, minúsculas), a mesma regra do `resolve_category_id`. Não se usa o `legacy_id`: ele coincide nas categorias atuais, mas a 500cc vem com `legacy_id = -1` na Broadcast (1990).

| Campo | Tipo | Descrição |
|---|---|---|
| `name` | string | Nome da equipe naquela temporada (com patrocinador). |
| `legacy_id` | int | ID numérico antigo da equipe na Broadcast (ex.: Aprilia Racing = 21). |
| `type` | string | `Official` (11) ou `Test` (2: `HRC Test Team` e `Yamaha Factory Racing Team`) em 2025. |
| `constructor` | objeto | `{id, name, legacy_id}` do fabricante. |
| `category` | objeto | `{id, name, legacy_id}` da categoria **na Broadcast** (`737ab122...` para a MotoGP). |
| `riders` | lista | Elenco: perfis resumidos dos pilotos (`id`, `name`, `surname`, `legacy_id`, `country`, `birth_date`, `current_career_step` etc.), **sem** `career`. |
| `color`, `text_color`, `picture`, `background_picture`, `social_media`, `published` | vários | Apresentação; sem uso analítico. |

### Chave composta

**O `id` da equipe na Broadcast se repete entre temporadas, mas o elenco muda.** Em 2024 e 2025, 11 das 13 equipes da MotoGP têm o mesmo `id`. Exemplo: a Pertamina Enduro VR46 tem o mesmo `id` nos dois anos, com Bezzecchi, Di Giannantonio, Iannone e Pirro em 2024 e Di Giannantonio e Morbidelli em 2025. Com `_id = id`, a coleta de um ano sobrescreveria o elenco do outro. Por isso a ingestão gera:

```text
id = "{season_year}:{category_id}:{team_id}"
```

O `category_id` é o da **Results** API, para manter o mesmo valor do campo nas outras coleções.

### Campos acrescentados pela ingestão

| Campo | Tipo | Origem |
|---|---|---|
| `id` (e `_id`) | string | Chave composta (acima). Substitui o `id` original no documento. |
| `team_id` | string | Cópia do `id` original da equipe na Broadcast. É o valor que aparece em `riders.career[].team.id`. |
| `season_year` | int | Temporada consultada. |
| `category_id` | string | Categoria consultada (UUID da Results). |

### Observações

- MotoGP 2025: 13 equipes, 35 entradas de piloto e **32 pilotos distintos**. Os 29 pilotos da classificação estão todos lá; os outros 3 (Dovizioso, Pedrosa e Joel Esteban) não correram.
- **Um piloto pode aparecer em mais de uma equipe:** Nakagami em 3 (Honda HRC Castrol, Honda LCR e HRC Test Team) e Pol Espargaró em 2. O elenco lista todas as inscrições da temporada, inclusive substitutos, wildcards e pilotos de teste.
- **Os perfis embutidos são de hoje.** O `current_career_step` dos pilotos do elenco é de 2025 ou 2026 conforme o piloto, e não da temporada consultada. A equipe de cada corrida vem de `classification.team`.
- **Elencos antigos incompletos:** em 2004, o `/teams` traz 11 equipes e 18 pilotos, contra 29 pilotos no standings daquele ano.
- Como o standings, é um **retrato**: o upsert sobrescreve o elenco a cada execução.

## Coleção `riders`

Um documento por piloto: o perfil completo da **Broadcast API**, `GET /riders/{id}`. A coleta faz uma requisição por piloto que aparece na `classification` da temporada e categoria (29 em 2025). A lista de pilotos vem do **banco** (`storage.distinct_rider_uuids()`, um `distinct` de `rider.riders_api_uuid`), e não das sessões coletadas na execução, para que a retomada (que pula sessões) não deixe pilotos de fora. Os perfis são sempre recoletados: o `career` ganha uma entrada a cada temporada.

### Chave e ligação com a Results API

- `_id` = `id` = UUID do piloto na Broadcast. **Não é o `rider.id` da Results.**
- A ligação é `classification.rider.riders_api_uuid` → `riders._id`. Conferido em 10/11/2026: os 29 `_id` são exatamente os `riders_api_uuid` distintos da classificação de 2025.
- O `legacy_id` também coincide entre as duas APIs (Marc Márquez: 7444).

**A ingestão não acrescenta campos** (só os metadados). O perfil não depende da temporada; o que muda por ano está em `career`. Um `season_year` no perfil seria sobrescrito a cada temporada coletada.

| Campo | Tipo | Descrição |
|---|---|---|
| `name`, `surname`, `nickname` | string | Nome. Alguns valores têm espaço sobrando (`'Aldeguer '`). |
| `legacy_id` | int | ID numérico antigo; igual na Results (`rider.legacy_id`). |
| `country` | objeto | `{iso, name, flag}`. |
| `birth_date` | string | `'AAAA-MM-DD'`. |
| `birth_city`, `birth_country` | string | Local de nascimento. |
| `start_year` | int | Ano de estreia no mundial. |
| `retired`, `retired_year`, `legend` | bool / int | Situação **atual** do piloto. |
| `years_old` | int | Idade **na data da consulta**. |
| `physical_attributes` | objeto | `{height, weight}` atuais (ex.: Bastianini 168 cm, 64 kg). |
| `career` | lista | Uma entrada por inscrição (ver abaixo). |
| `biography`, `social_media`, `merchandise_url`, `legend_picture`, `famous_attributes`, `published` | vários | Apresentação; sem uso analítico. |

### `career`

Cada entrada tem `{id, season, number, sponsored_team, team, category, type, in_grid, current, short_nickname, pictures}`. O `team` é a equipe na Broadcast (`{id, name, legacy_id, type, constructor, category, ...}`), e o `team.id` dele é o `team_id` da coleção `teams`.

- De 7 a 24 entradas por piloto em 2025, incluindo a **temporada seguinte** (2026), quando já anunciada.
- **Mais de uma entrada por temporada é possível:** na MotoGP 2025, Nakagami tem 3 e Pol Espargaró tem 2; os outros 27 pilotos têm 1.
- `type`: `Official` (90), `Substitute` (19), `Wildcard` (6) e `Test` (3) em 414 entradas. Nas outras **296 vem `null`**, principalmente nas temporadas antigas. Não dá para distinguir wildcard ou substituto em toda a carreira.
- **O `career` é a inscrição, não a equipe de cada corrida.** Para os pares piloto × equipe da classificação de 2025, 28 de 34 batem pelo nome com o `career` daquele ano. Das 6 diferenças, 4 são só de grafia (`Monster Energy Yamaha MotoGP Team` × `Monster Energy Yamaha MotoGP™`; `Trackhouse MotoGP Team` × `Trackhouse MotoGP™ Team`) e 2 são substitutos: Aleix Espargaró correu pela Honda HRC Castrol e Augusto Fernández pela Prima Pramac, mas o `career` só os lista na HRC Test Team e na Yamaha Factory Racing Team. A equipe de cada corrida vem sempre de `classification.team`.

### Cuidados para a análise

- `years_old`, `physical_attributes`, `retired` e `career[].current` mudam com o tempo e refletem o **momento da consulta**. A idade na corrida deve ser calculada a partir de `birth_date` e da data da sessão.
- Entradas do `career` de temporadas posteriores à corrida analisada não devem ser usadas como atributo (vazamento).

## Inconsistências entre coleções

| Dado | `events` | `sessions` | `classification` | `grid` |
|---|---|---|---|---|
| Ano da temporada | `season.year`: int `2025` | `event.season`: **string** `'2025'` | `season_year`: int `2025`; `team.season.year`: int | `season_year`: int; `event.season`: **string** |
| Circuito | `circuit`: objeto | `circuit`: string (nome); `event.circuit`: objeto | — | `event.circuit`: objeto |
| Datas | `date_start`/`date_end`: string `'AAAA-MM-DD'` | `date`: string ISO com fuso | — | — |
| Equipe | — | — | `team`: objeto | `team_name`: string |

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
| `results` | Analítica | Uma linha por piloto × sessão, com campos achatados e tipados (tempos em segundos, datas como `Date`) |
| `ingestion_runs` | Controle | Início, fim, status, contagens e erros de cada execução |

## Results API × Broadcast API

`riders` e `teams` vêm de outra API do mesmo domínio (a "Broadcast API"), que usa **outros IDs** para as mesmas entidades:

| Entidade | Results API | Broadcast API | Como ligar |
|---|---|---|---|
| Categoria MotoGP | `e8c110ad-64aa-4e8e-8a86-f2f152f6a942` (o mesmo em 2004, 2024 e 2025) | `737ab122-76e1-4081-bedb-334caaa18c70` (`GET /categories?seasonYear=`) | Nome normalizado (sem `™`). O `legacy_id` coincide nas categorias atuais (3), mas a 500cc vem com -1 na Broadcast |
| Equipe Ducati Lenovo | Um `team.id` por piloto e por temporada (2025: `4728a8ee...`/legacy 24 para Márquez, `c069c64a...`/legacy 19 para Bagnaia) | `892fff2f-7402-4fbd-99fb-5fd567d8a80c` (legacy 15, o mesmo em 2024 e 2025) | Sem ligação direta: nem `id`, nem `legacy_id`, nem o nome batem sempre (`CASTROL Honda LCR` × `Honda LCR`). Caminho indireto: piloto → `riders.career[]` (temporada) → `team.id` → `teams.team_id` |
| Piloto | `rider.id` | `id` = `rider.riders_api_uuid` da classificação | `riders_api_uuid` |
| Temporada | Um UUID por ano (2004: `6c0e0734...`, 2024: `dd12382e...`, 2025: `ae6c6f0d...`) | — | — |
| Evento | `id` | — | `toad_api_uuid` do evento aponta para o evento na Broadcast API |

Cuidados com a Broadcast API:
- O `/riders` (lista) traz só a temporada **atual**. Por isso a coleta usa o `/riders/{id}` para cada piloto da classificação, e o `/teams` para os elencos, que também listam pilotos de teste e substitutos (em 2025, a Ducati Lenovo tem 4).
- O `current_career_step` do piloto (no `/riders`) é a equipe **de hoje**, não a da época da corrida. A equipe de cada corrida vem de `classification.team`. Já o `/riders/{id}` traz `career`, uma lista com uma entrada por temporada (`season`, `number`, `sponsored_team`, `team`, `category`, `type`, `current`), que dá a equipe de cada ano. Dentro do `career`, o `current` é volátil como o `season.current` dos eventos.
- A lista de inscritos de um evento (`/event/{id}/entry`, citada na documentação comunitária) não está disponível: o caminho documentado devolve 400 e a variante com `/results` é bloqueada pelo firewall da API (424 "WAF block detected"), conferido em 29/10/2026.
- As estatísticas de carreira (`/riders/{legacy_id}/statistics`) são agregados atuais e não servem como atributo de previsão (vazamento).

## Pendências

A confirmar ao coletar outras temporadas e categorias:

- **ID do piloto:** resolvida em 03/11/2026 (ver [IDs do piloto](#ids-do-piloto)). A chave é o `rider.id`.
- **Equipe:** o `team.id` da Results API não identifica a equipe (ver [Equipe](#equipe-team)). O `teams.team_id` da Broadcast é estável entre anos e é o candidato a identificador, mas a ligação com a Results só existe pelo `career` do piloto, que falha para substitutos (ver [`career`](#career)). Falta decidir a regra na camada analítica e conferir se a classificação das sessões antigas também vem com `team: null`.
- **Elencos antigos:** o `/teams` de 2004 traz 18 pilotos contra 29 no standings. Conferir a cobertura em outras temporadas antes de usar `teams` em anos antigos.
- **Campos nulos por época no standings:** em 2024, `sprint_wins`, `sprint_podiums` e `sprint_last_positions` vêm `null` para todos os pilotos, apesar de ter havido sprints. Em 2004, `team`, `rider.number`, `race_wins`, `podiums` e `last_positions` vêm `null`. Não usar esses campos como atributo sem conferir a cobertura por temporada.
- **ID do circuito:** conferir se `circuit.id` é o mesmo em anos diferentes.
- **Pontos em temporadas antigas:** o standings traz `points` em 2004 e 2024 (Rossi, 2004: 304, que confere com o resultado oficial). Falta conferir se a classificação das **sessões** também traz `points` antes de 2025.
- **Sessões em temporadas antigas e em Moto2/Moto3:** conferir os valores reais de `type` e `number`.
- **Outros valores de `status`:** até agora só apareceram `INSTND` e `OUTSTND`.
- **Grid:** conferir se a `qualifying_position` já inclui punições de grid e identificar os 10 casos de 2025 que estão no grid mas não na `RAC`.
