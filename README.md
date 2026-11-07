# AEOSSP — Gurobi ILP Solver

Solver exato (Programação Linear Inteira) para o **Agile Earth Observation Satellite Scheduling Problem** (AEOSSP), usando [Gurobi](https://www.gurobi.com/).
Serve como baseline de comparação com os resultados da metaheurística RKO.

## Descrição do problema

O AEOSSP consiste em selecionar um subconjunto de oportunidades de aquisição de imagens por satélites ágeis, maximizando a pontuação total, sujeito a:

1. **Limite por request** — cada request (`ID`) tem um número máximo de aquisições: `max(stereo + 1, strips)`
2. **Sem sobreposição temporal** — duas aquisições no mesmo satélite não podem ter janelas de tempo sobrepostas
3. **Manobra factível** — aquisições consecutivas no mesmo satélite precisam de tempo suficiente para a rotação angular (2.5°/s)
4. **Stereo enforcement** — aquisições stereo exigem pelo menos um parceiro da mesma request em órbita diferente (Δt > 600 s)

## Estrutura do projeto

```
├── config.py              # Definição das 36 instâncias, caminhos, constantes físicas
├── instance_parser.py     # Parser dos arquivos CSV de instância
├── model.py               # Construção e resolução do modelo ILP (Gurobi)
├── solver.py              # Resolve uma instância e escreve resultados
├── run_all.py             # Runner batch para todas as instâncias
├── compare_results.py     # Comparação Gurobi × RKO
├── test_model.py          # Testes com instâncias sintéticas
├── requirements.txt       # Dependências Python
├── Results/               # Saída (Evaluation_Gurobi_*.csv)
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
python solver.py 250_8h_1sat
```

### Resolver todas as 36 instâncias

```bash
python run_all.py
```

### Resolver um subconjunto

```bash
python run_all.py --tags 250_8h_1sat 250_8h_2sat 500_24h_4sat
```

### Comparar Gurobi × RKO

```bash
python compare_results.py
python compare_results.py --output comparison.csv
```

### Rodar os testes

```bash
python test_model.py
```

## Formato de saída

Cada instância gera `Results/Evaluation_Gurobi_<tag>.csv` no formato `section,metric,value`:

```csv
section,metric,value
INSTANCE,tag,250_8h_1sat
INSTANCE,num_acquisitions,191
INSTANCE,time_limit_seconds,60
SOLVER,name,Gurobi
SOLVER,status,OPTIMAL
SOLVER,gap,0.000000
SOLUTION,objective_value,12345.678000
SOLUTION,num_selected_acquisitions,42
```

Além disso, `Results/Solution_Gurobi_<tag>.txt` contém os índices das aquisições selecionadas (um por linha).

## Formulação ILP

| Componente | Formulação |
|-----------|-----------|
| Variáveis | x_i ∈ {0,1} para cada aquisição i |
| Objetivo | max Σ (score_scenario_i · x_i) |
| Restrição 1 | ∀ grupo ID: Σ x_i ≤ max(stereo+1, strips) |
| Restrição 2 | ∀ (i,j) mesmo satélite com overlap: x_i + x_j ≤ 1 |
| Restrição 3 | ∀ (i,j) mesmo satélite com gap < ângulo/2.5: x_i + x_j ≤ 1 |
| Restrição 4 | ∀ i com stereo > 0: x_i ≤ Σ x_j (j ∈ parceiros) |

O ângulo entre duas posições é calculado como a distância angular (great-circle) entre as coordenadas do satélite, convertidas de (lat, lon, alt=550 km) para cartesianas ECEF.

## Instâncias

| Tag | \|A\| | TimeLimit (s) |
|-----|-------|--------------|
| 250_8h_1sat | 191 | 60 |
| 250_8h_2sat | 362 | 60 |
| 250_8h_3sat | 578 | 60 |
| 250_8h_4sat | 733 | 60 |
| 250_12h_1sat | 214 | 60 |
| 250_12h_2sat | 401 | 60 |
| 250_12h_3sat | 627 | 60 |
| 250_12h_4sat | 855 | 60 |
| 250_24h_1sat | 718 | 60 |
| 250_24h_2sat | 1404 | 150 |
| 250_24h_3sat | 2219 | 300 |
| 250_24h_4sat | 2891 | 300 |
| 500_8h_1sat | 383 | 60 |
| 500_8h_2sat | 737 | 60 |
| 500_8h_3sat | 1196 | 150 |
| 500_8h_4sat | 1550 | 150 |
| 500_12h_1sat | 416 | 60 |
| 500_12h_2sat | 791 | 60 |
| 500_12h_3sat | 1300 | 150 |
| 500_12h_4sat | 1737 | 150 |
| 500_24h_1sat | 1331 | 150 |
| 500_24h_2sat | 2651 | 300 |
| 500_24h_3sat | 4307 | 600 |
| 500_24h_4sat | 5546 | 600 |
| 1000_8h_1sat | 930 | 60 |
| 1000_8h_2sat | 1750 | 150 |
| 1000_8h_3sat | 2629 | 300 |
| 1000_8h_4sat | 3513 | 600 |
| 1000_12h_1sat | 999 | 60 |
| 1000_12h_2sat | 1870 | 150 |
| 1000_12h_3sat | 2872 | 300 |
| 1000_12h_4sat | 3912 | 600 |
| 1000_24h_1sat | 2755 | 300 |
| 1000_24h_2sat | 5516 | 600 |
| 1000_24h_3sat | 8733 | 900 |
| 1000_24h_4sat | 11353 | 900 |
