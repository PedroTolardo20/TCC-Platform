# RAV - Robô Autônomo de Varejo 

## Descrição do projeto
O presente trabalho tem como objetivo o desenvolvimento de um robô móvel autônomo capaz de realizar tarefas de navegação e manipulação de objetos de forma independente em um ambiente simulado de varejo. O sistema proposto busca integrar técnicas de robótica móvel, visão computacional e manipulação robótica, permitindo a execução de atividades relacionadas à logística e organização de produtos.

A proposta do projeto visa reproduzir operações comuns em ambientes comerciais, como deslocamento autônomo, identificação de objetos e manipulação de itens, contribuindo para estudos voltados à automação no setor varejista.

Para a definição da arquitetura mecânica e funcional do robô, foi realizada uma análise comparativa de soluções robóticas semelhantes presentes no mercado e na literatura, considerando critérios como mobilidade, estabilidade estrutural, capacidade de manipulação e modularidade do sistema.

Com base nessa análise, definiu-se a arquitetura mecânica apresentada na figura a seguir.
<div align="center">
  <img width="400" alt="image" src="https://github.com/user-attachments/assets/0e0b22d1-9cb5-40c8-a2cf-937e2103f875" />
</div>


## Modelagem

Após a definição da arquitetura do sistema robótico, iniciou-se o processo de modelagem mecânica da plataforma móvel e do manipulador robótico, utilizando ferramentas CAD para o desenvolvimento estrutural e validação dimensional dos componentes.

O projeto foi dividido em dois subsistemas principais:

- Base móvel, responsável pela locomoção e estabilidade do robô;
- Manipulador robótico, responsável pelas tarefas de alcance e manipulação de objetos.

### Base móvel

A base móvel foi projetada visando estabilidade estrutural, distribuição adequada de massa e suporte para os componentes eletrônicos e mecânicos do sistema. Além disso, foram considerados aspectos relacionados à mobilidade em ambientes internos, permitindo deslocamento eficiente em corredores e áreas simuladas de varejo.

A modelagem da estrutura da base móvel é apresentada abaixo.

<div align="center">
  <img width="1294" height="825" alt="image" src="https://github.com/user-attachments/assets/ae9e3110-f8f4-4565-b4f4-29050c7082e0" />
</div>

### Manipulador
Para o desenvolvimento do sistema de manipulação, foi utilizado como referência o repositório <a href="https://github.com/Robotawi/rrr-arm">rrr-arm</a>. Entretanto, o modelo URDF do manipulador foi adaptado e modificado para atender aos requisitos específicos deste trabalho, considerando características mecânicas, estruturais e funcionais necessárias para integração com a plataforma móvel desenvolvida.

O manipulador foi projetado com o objetivo de executar movimentos de alcance e posicionamento de objetos em ambientes simulados de varejo, possibilitando futuras implementações de algoritmos de controle e planejamento de trajetória.

A modelagem do manipulador robótico é apresentada na figura abaixo.

<div align="center">
  <img width="1293" height="825" alt="image" src="https://github.com/user-attachments/assets/cfacb8ef-c2ac-484a-9585-314082d3645f" />
</div>

## Estrutura Final 
Após a integração entre a base móvel e o manipulador robótico, obteve-se a estrutura completa do robô autônomo de varejo, conforme ilustrado nas figuras a seguir.

<div align="center"> <img width="1294" height="825" alt="Estrutura completa do robô" src="https://github.com/user-attachments/assets/4495b30b-c896-495a-b67a-163586738237" /> </div> <div align="center"> <img width="315" height="566" alt="Vista lateral do robô" src="https://github.com/user-attachments/assets/31862cb9-f471-4738-aa35-2844f1d062ec" /> </div>
