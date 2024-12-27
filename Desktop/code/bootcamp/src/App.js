import React from 'react';
import CardEditor from './CardEditor';
import CardViewer from './CardViewer';

class App extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      cards: [
        { front: 'front1', back: 'back1' },
        { front: 'front2', back: 'back2' },
      ],
      editor: true, 
    };
  }

  addCard = (card) => {
    const cards = [...this.state.cards, card];
    this.setState({ cards });
  };

  deleteCard = (index) => {
    const cards = [...this.state.cards];
    cards.splice(index, 1);
    this.setState({ cards });
  };

  switchMode = () => {
    this.setState((prevState) => ({ editor: !prevState.editor }));
  };

  render() {
    if (this.state.editor) {
      return (
        <CardEditor
          addCard={this.addCard}
          cards={this.state.cards}
          deleteCard={this.deleteCard}
          switchMode={this.switchMode}
        />
      );
    } else {
      return (
        <CardViewer
          cards={this.state.cards} 
          switchMode={this.switchMode}
        />
      );
    }
  }
}

export default App;
