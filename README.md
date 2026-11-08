# AEOSSP — Gurobi ILP Solver

Solver exato (Programação Linear Inteira) para o **Agile Earth Observation Satellite Scheduling Problem** (AEOSSP), usando [Gurobi](https://www.gurobi.com/).
Serve como baseline de comparação com os resultados da metaheurística RKO.

## Descrição do problema

O AEOSSP consiste em selecionar um subconjunto de oportunidades de aquisição de imagens por satélites ágeis, maximizando a pontuação total, sujeito a:

1. **Limite por request** — cada request (`ID`) tem um número máximo de aquisições: `max(stereo + 1, strips)`
2. **Sem sobreposição temporal** — duas aquisições no mesmo satélite não podem ter janelas de tempo sobrepostas
3. **Manobra factível** — aquisições consecutivas no mesmo satélite precisam de tempo suficiente para a rotação angular (2.5°/s). O ângulo é calculado entre os vetores de visada (satélite → alvo) em coordenadas cartesianas 3D
4. **Stereo enforcement** — aquisições stereo exigem pelo menos um parceiro válido (mesmo ID, ambos stereo > 0, ângulo de visada entre 15° e 20°)

## Estrutura do projeto

```
├── config.py              # Definição das 36 instâncias, caminhos, constantes físicas
├── instance_parser.py     # Parser dos CSVs, deduplicação, binarização de stereo
├── model.py               # Construção e resolução do modelo ILP (Gurobi)
├── solver.py              # Resolve uma instância e escreve resultados
├── run_all.py             # Runner batch com seleção flexível de instâncias
├── compare_results.py     # Comparação Gurobi × RKO
├── test_model.py          # Testes com instâncias sintéticas (11 testes)
├── requirements.txt       # Dependências Python
├── Results/               # Saída (Evaluation_Gurobi_*.csv, summary_gurobi.csv)
└── Logs/                  # Logs do Gurobi (gitignored)
```

## Pré-requisitos

- Python ≥ 3.10
- Licença Gurobi válida (acadêmica ou comercial)

```bash
pip install -r requirements.txt
```

## Configuração de caminhos

O solver lê as instâncias diretamente do diretório do framework RKO (sem copiar).
Os caminhos padrão assumem esta estrutura:

```
~/Desktop/renata/
├── gurobi/
│   └── gurobi_aeossp/    ← este repositório
└── RKO-solver-Framework_v2.0/
    ├── Instances/         ← arquivos de instância
    └── Results_linux/     ← resultados do RKO
```

Para sobrescrever, use variáveis de ambiente ou argumentos CLI:

| Variável de ambiente    | Argumento CLI       | Default (relativo)                               |
|------------------------|--------------------|-------------------------------------------------|
| `AEOSSP_INSTANCES_DIR` | `--instances-dir`  | `../../RKO-solver-Framework_v2.0/Instances`     |
| `AEOSSP_RESULTS_DIR`   | `--results-dir`    | `./Results`                                      |
| `AEOSSP_RKO_RESULTS_DIR`| `--rko-dir`       | `../../RKO-solver-Framework_v2.0/Results_linux` |
| `AEOSSP_LOG_DIR`       | `--log-dir`        | `./Logs`                                         |

## Uso

### Resolver uma instância

```bash
python3 solver.py 250_8h_1sat
```

### Resolver instâncias específicas

```bash
python3 run_all.py 250_8h_1sat 250_8h_2sat
```

### Resolver um grupo por prefixo

```bash
python3 run_all.py --group 250_8h      # todas 250_8h_*
python3 run_all.py --group 250          # todas 250_*
python3 run_all.py --group 250_8h 500_8h  # combinar prefixos
```

### Listar instâncias disponíveis (ordenadas por |A|)

```bash
python3 run_all.py --list
```

### Resolver todas as 36 instâncias

```bash
python3 run_all.py --all
```

> **Nota:** O `summary_gurobi.csv` acumula resultados entre execuções — novas entradas atualizam as existentes sem apagar as anteriores.

### Comparar Gurobi × RKO

```bash
python3 compare_results.py
python3 compare_results.py --output comparison.csv
```

### Rodar os testes

```bash
python3 test_model.py
```

## Pipeline de dados

O parser (`instance_parser.py`) aplica os mesmos pré-processamentos que o RKO:

1. **Binarização do stereo**: valores `stereo ∈ {2, 3, …}` são clipados para `1`
2. **Deduplicação**: linhas com mesmos `(ID, satellite, time, satellite_location)` são removidas
3. **Coordenadas 3D**: posições do satélite (lat, lon, alt=694 km) e do alvo (lat, lon, ground) são convertidas em cartesianas ECEF

## Formato de saída

Cada instância gera `Results/Evaluation_Gurobi_<tag>.csv` no formato `section,metric,value`, compatível com os arquivos do RKO:

```csv
section,metric,value
scenario,requests,19
scenario,attempts,191
scenario,stereo_pairs,24
scenario,avg_angle,19.854630
...
solution,acquisitions,29
solution,total_score,16.223301
solution,ofv,-16.223301
...
gurobi,status,OPTIMAL
gurobi,is_optimal,True
gurobi,gap,0.000000
gurobi,solver_time,0.0074
...
```

As seções são: `scenario` (dados após dedup), `scenario_raw` (dados brutos pré-dedup), `solution` (aquisições selecionadas), `gurobi` (métricas do solver).

`Results/Solution_Gurobi_<tag>.txt` contém os índices das aquisições selecionadas (um por linha).

## Formulação ILP

| Componente | Formulação |
|-----------|-----------|
| Variáveis | x_i ∈ {0,1} para cada aquisição i |
| Objetivo | max Σ (score_scenario_i · x_i) |
| Restrição 1 | ∀ grupo ID: Σ x_i ≤ max(stereo+1, strips) |
| Restrição 2 | ∀ (i,j) mesmo satélite com overlap temporal: x_i + x_j ≤ 1 |
| Restrição 3 | ∀ (i,j) mesmo satélite com dur_i + ângulo/2.5 > Δt: x_i + x_j − Σ x_k ≤ 1 (lifted) |
| Restrição 4 | ∀ i com stereo > 0: x_i ≤ Σ x_j (j ∈ parceiros com ângulo de visada ∈ [15°, 20°]) |

- O **ângulo de manobra** é calculado entre os vetores de visada (sat_xyz − req_xyz) das duas aquisições, usando coordenadas cartesianas com `R = 6371 km` e `h = 694 km`
- A **restrição de manobra lifted** permite que pares não-adjacentes sejam selecionados quando existem aquisições intermediárias (igualando o comportamento do decoder RKO)
- O solver roda como método **exato sem limite de tempo**, otimizando até provar optimalidade

## Instâncias

36 instâncias organizadas por número de requests × horizonte × satélites:

| Prefixo | |A| (range) | Instâncias |
|---------|------------|-----------|
| 250_8h  | 191 – 733   | 1sat, 2sat, 3sat, 4sat |
| 250_12h | 214 – 855   | 1sat, 2sat, 3sat, 4sat |
| 250_24h | 718 – 2891  | 1sat, 2sat, 3sat, 4sat |
| 500_8h  | 383 – 1550  | 1sat, 2sat, 3sat, 4sat |
| 500_12h | 416 – 1737  | 1sat, 2sat, 3sat, 4sat |
| 500_24h | 1331 – 5546 | 1sat, 2sat, 3sat, 4sat |
| 1000_8h | 930 – 3513  | 1sat, 2sat, 3sat, 4sat |
| 1000_12h| 999 – 3912  | 1sat, 2sat, 3sat, 4sat |
| 1000_24h| 2755 – 11353| 1sat, 2sat, 3sat, 4sat |
