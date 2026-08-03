# Sistema modular de armazenamento de cartas (TCG)

Modelo 3D paramétrico, gerado por script no Blender e pronto para impressão 3D.
Cada módulo é uma caixa com gaveta e **sulcos em rabo de andorinha** nas quatro
faces externas — os módulos se unem entre si (empilhados ou lado a lado) por meio
de uma chave que desliza nos sulcos.

![preview](preview.png)

## Peças

| Peça | Arquivo | O que é |
|---|---|---|
| Casco | `stl/shell.stl` | corpo do módulo, com os sulcos de encaixe |
| Gaveta | `stl/drawer.stl` | bandeja + frente + puxador + porta-etiqueta |
| Chave | `stl/key.stl` | clipe de rabo de andorinha duplo que trava dois módulos |
| Etiqueta | `stl/label.stl` | token liso para o porta-etiqueta |
| Etiqueta escrita | `stl/label_commons.stl` | exemplo de token com texto em relevo |

Um módulo completo = 1 casco + 1 gaveta + 1 etiqueta. As chaves são consumíveis:
use 2 por junta (uma em cada sulco da face) — ou as 3 disponíveis nas laterais,
se quiser uma união bem rígida.

## Dimensões (configuração padrão)

| | mm |
|---|---|
| Externo do casco (L × P × A) | 80 × 195 × 103,4 |
| Profundidade total com a frente e o porta-etiqueta | 200,6 (o puxador avança outros 16) |
| Espaço interno por gaveta (L × P × A) | 70 × 190 × 95 |
| Capacidade | ~306 cartas com sleeve duplo (~422 com sleeve simples) |
| Parede do casco | 3,0 mm |
| Parede/fundo da gaveta | 1,6 mm |
| Folga gaveta ↔ casco | 0,4 mm por lado |

O espaço interno de 70 × 95 mm acomoda carta padrão de 63 × 88 mm já com sleeve
duplo (perfect fit + sleeve normal), com folga.

### Sulcos de encaixe

Rabo de andorinha com **14 mm** de abertura na superfície, alargando para
**17,6 mm** no fundo, **1,8 mm** de profundidade e flancos a **45°**
(auto-sustentáveis, imprimem sem suporte). São 2 sulcos no topo e na base e 3 em
cada lateral, correndo por toda a profundidade — a chave entra deslizando pela
traseira.

Como topo/base e as duas laterais usam as mesmas posições, qualquer módulo encaixa
em qualquer outro, em qualquer das duas direções.

| | mm | flag |
|---|---|---|
| Abertura na superfície | 14,0 | `--g-open` |
| Profundidade | 1,8 | `--g-depth` |
| Alargamento por lado | 1,8 | `--g-flare` |
| Largura no fundo | 17,6 | (derivada) |
| Sulcos no topo/base | 2 | `--grooves-top` |
| Sulcos por lateral | 3 | `--grooves-side` |

Dois limites decidem o tamanho máximo do encaixe, e `validate.py` confere os
dois:

- **A profundidade é limitada pela parede do casco.** Precisam sobrar ao menos
  1,2 mm de material atrás do sulco, então com `s_wall` de 3,0 mm o máximo é
  1,8 mm — que é o padrão. Para ir mais fundo, aumente `--s-wall` junto (isso
  muda as cotas externas do módulo).
- **A largura é limitada pelo sulco vizinho.** No padrão sobram 9,1 mm de
  material entre dois sulcos do topo e 8,2 mm entre dois da lateral. Sulcos
  largos demais se encostariam e virariam um rasgo só — a malha continuaria
  fechada e a chave continuaria entrando, então só a conta pega o problema.

Como o alargamento sai do sulco, um encaixe maior gasta *menos* filamento: o
casco padrão caiu de ~205 cm³ para ~174 cm³.

### Porta-etiqueta

A frente da gaveta tem um bolso **saliente**, aplicado por cima da porta (não a
atravessa), para um token de identificação trocável.

| | mm |
|---|---|
| Bolso, externo | 59,2 × 15,3, avançando 2,6 da frente |
| Vão do token | 56 × 16 × 1,8 |
| Token | 55,7 × 15,7 × 1,6 |
| Sobreposição da moldura | 1,85 por lado |
| Texto em relevo | 0,6 |

**Como troca:** o bolso tem paredes nas laterais e embaixo e é **aberto em cima**
— o token desce por ali, como um cartão entrando num porta-crachá. A moldura
frontal o segura pela frente em 87% da altura, e ele sobra 2 mm acima do bolso,
que é onde você pega para puxar. Não precisa abrir a gaveta nem desmontar nada.

Ser aberto em cima é também o que torna a peça fácil de imprimir: as paredes
laterais são verticais e o fundo é um ressalto de só 2,6 mm, então **não existe
nenhuma ponte** no porta-etiqueta.

O texto fica 0,2 mm recuado em relação à frente do bolso, protegido de esbarrão.

**Gerando tokens escritos:**

```bash
blender --background --python tcg_storage.py -- --export \
    --label-text "Commons" \
    --label-text "Cheap sleeves" \
    --label-text "Dragonshields"
```

Cada `--label-text` gera um `stl/label_<texto>.stl`. O texto é dimensionado
automaticamente para caber na janela. Para outra fonte, use
`--label-font /caminho/para/fonte.ttf`. Para gavetas lisas, `--no-label`. Se
preferir o token rente ao bolso em vez de sobrando 2 mm, ajuste `label_grip`
na classe `Params`.

Para ter contraste de cor como na foto de referência, imprima o token deitado e
programe uma **troca de filamento na altura em que o relevo começa** (1,6 mm) —
o fatiador chama isso de "color change" ou "filament change". Sem troca de cor,
o relevo já é legível de perto.

## Como gerar / editar o modelo

O modelo é gerado por script, então qualquer medida pode ser alterada sem
modelar nada à mão.

Os scripts (`tcg_storage.py`, `validate.py`, `preview.py`) usam o módulo `bpy`,
que só existe dentro do interpretador do Blender — por isso são executados **pelo
Blender**, não pelo `python` do sistema:

```bash
blender --background --python tcg_storage.py -- --export
```

O `--` é obrigatório: tudo que vem depois dele é repassado ao script, tudo que
vem antes é consumido pelo Blender. Rodar `python tcg_storage.py` direto falha
com `ModuleNotFoundError: No module named 'bpy'`, a menos que você tenha
instalado o Blender como módulo Python (`pip install bpy`, que exige uma versão
do Python compatível com o build do pacote).

Isso escreve os STL em `stl/`. Para abrir a cena no Blender e ajustar à mão:

```bash
blender --background --python tcg_storage.py -- --save-blend tcg_storage.blend
blender tcg_storage.blend
```

O arquivo `tcg_storage.blend` já vem pronto no repositório, com as três peças
separadas lado a lado.

### Parâmetros mais usados

```bash
blender --background --python tcg_storage.py -- --export --depth 150          # módulo mais curto
blender --background --python tcg_storage.py -- --export --drawers 3          # 3 gavetas no mesmo casco
blender --background --python tcg_storage.py -- --export --card-w 72          # cartas mais largas
blender --background --python tcg_storage.py -- --export --gap 0.3            # gaveta mais justa
blender --background --python tcg_storage.py -- --export --key-clear 0.15     # chave mais firme
blender --background --python tcg_storage.py -- --export --g-open 18          # rabo de andorinha mais largo
blender --background --python tcg_storage.py -- --export --s-wall 4 --g-depth 2.6 --g-flare 2.6   # encaixe mais fundo
blender --background --python tcg_storage.py -- --export --label-text "Raras" # token escrito
blender --background --python tcg_storage.py -- --export --no-label           # gaveta lisa
blender --background --python tcg_storage.py -- --help                        # lista completa
```

Se for usar muito, vale um atalho no shell:

```bash
alias tcg='blender --background --python tcg_storage.py --'
tcg --export --depth 150
```

Todas as cotas estão na classe `Params`, no topo de `tcg_storage.py`, com
comentários.

| `--depth` | altura do casco ao imprimir em pé | capacidade (sleeve duplo) |
|---|---|---|
| 150 | 155 mm | ~241 cartas |
| 190 (padrão) | 195 mm | ~306 cartas |
| 220 | 225 mm | ~354 cartas |

### Verificação

```bash
blender --background --python validate.py
```

Confere, por interseção booleana real, que a gaveta fechada não colide com o
casco, que a chave desliza nos sulcos do topo, da base e das laterais, que os
tokens encaixam no bolso, que dois módulos empilhados/lado a lado não se
interpenetram e que todas as malhas são fechadas (manifold). Também confere as
cotas: material atrás do sulco, ângulo dos flancos e distância entre sulcos
vizinhos.

Ele aceita as mesmas flags de cota do gerador, então dá para conferir a
configuração que você vai imprimir — rode isso depois de mudar qualquer
parâmetro:

```bash
blender --background --python validate.py -- --g-open 18 --drawers 3
```

### Preview

```bash
blender --background --python preview.py -- --out preview.png --stack 2
```

A cena sai montada: dois módulos empilhados, a gaveta de baixo aberta, uma chave
a meio caminho de entrar num sulco lateral e outra pairando sobre um sulco do
topo, na posição em que entraria para prender mais um módulo. O enquadramento é
calculado a partir do conteúdo da cena, então continua certo se você mudar as
cotas ou o número de módulos.

## Impressão

**Orientação** (importante — evita suportes e pontes):

- **Casco:** em pé, apoiado na traseira, com a boca para cima. Todas as paredes
  ficam verticais, os sulcos ficam verticais e não há nenhuma ponte sobre a
  cavidade. Exige ~200 mm de altura útil na impressora.
- **Gaveta:** deitada, fundo na mesa, frente em pé. A rampa inferior do puxador
  é de 45°, portanto ele se sustenta sozinho.
- **Chave:** deitada, eixo paralelo à mesa. Os flancos a 45° imprimem limpos.
- **Etiqueta:** deitada, texto para cima. Nessa posição o relevo sai limpo e é
  onde entra a troca de cor, se você quiser.

Nenhuma peça tem ponte: o maior balanço do projeto é o fundo do porta-etiqueta,
com 2,6 mm.

**Configuração sugerida:**

| | |
|---|---|
| Altura de camada | 0,2 mm |
| Perímetros | 3 |
| Preenchimento | 15% (giroide ou grid) |
| Suportes | nenhum |
| Material | PLA ou PETG |

Sem suporte em nenhuma peça. O casco padrão consome ~174 cm³ de material
(~210 g) e a gaveta ~126 cm³ (~155 g), então imprimir vários módulos leva tempo —
reduzir `--depth` é a forma mais direta de economizar.

**Ajuste de encaixe.** Impressoras variam. Se a gaveta ficar dura, aumente
`--gap` para 0,5; se ficar frouxa, use 0,3. Se a chave ficar apertada demais,
aumente `--key-clear` para 0,25; se ficar solta, reduza para 0,15. Imprima uma
chave e um token (poucos minutos cada) e teste antes de imprimir tudo.

## Estrutura do repositório

```
tcg_storage.py      gerador paramétrico (peças + tokens + exportação de STL)
validate.py         verificação de encaixes e de malha
preview.py          render de apresentação
tcg_storage.blend   cena Blender com as três peças
stl/                STL prontos para fatiar
preview.png         imagem de referência
```
