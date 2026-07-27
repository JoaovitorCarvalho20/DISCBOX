"""Ponto de entrada do executável empacotado: sempre abre a GUI.

Separado de main.py porque a CLI (main.py) não faz sentido num app de
clique-duplo — quem baixa o build pronto só quer a janela.
"""

from gui import main

if __name__ == "__main__":
    main()
