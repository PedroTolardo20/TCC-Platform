# Referência CAD do manipulador

Origem cinemática de cada junta: centro do horn do Dynamixel correspondente.

| Junta | Centro no CAD exportado (mm) |
|---|---:|
| J1 / shoulder_joint | `(0.000000, -47.471563, 733.684638)` |
| J2 / elbow_joint | `(0.000000, -47.441923, 1011.802711)` |
| J3 / wrist_joint | `(0.000000, -390.472111, 1011.787152)` |

Transforms usados no URDF, em metros:

- J1 → J2: `(0, 0.000029640, 0.278118073)`
- J2 → J3: `(0, -0.343030188, -0.000015559)`

As quatro meshes foram mantidas como fornecidas (em milímetros) e o URDF aplica
`scale="0.001 0.001 0.001"` mais os offsets necessários para levar o centro de
cada junta para a origem local do link correspondente.

Os valores acima descrevem a pose exportada do CAD e não substituem a futura
calibração física do zero de cada motor.
