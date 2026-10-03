# Catequese+

Sistema web para catequistas organizarem salas, alunos, chamadas, faltas, justificativas e anotações.

## Funcionalidades
- Cadastro e login de catequistas
- Senhas armazenadas com hash
- Criação de salas de catequese
- Cadastro de alunos apenas pelo nome
- Anotações por sala
- Chamada por data
- Status: Presente, Falta ou Falta justificada
- Campo de justificativa
- Histórico das chamadas
- Separação dos dados por usuário
- Layout responsivo/mobile first

## Rodar localmente
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Abra http://127.0.0.1:5000

## Produção
Defina uma `SECRET_KEY` forte. Para uso real com vários usuários e hospedagem permanente, prefira PostgreSQL via `DATABASE_URL` em vez do SQLite local.

## Deploy no Vercel
O projeto inclui `vercel.json` e suporta PostgreSQL por meio da variável `DATABASE_URL`.

Variáveis recomendadas em produção:
- `SECRET_KEY`: uma chave aleatória forte para as sessões do Flask.
- `DATABASE_URL`: conexão PostgreSQL persistente.

Sem `DATABASE_URL`, o Vercel usa SQLite em `/tmp` apenas para demonstração. Esses dados podem ser apagados quando a função serverless reiniciar.
