export type PlayableEvent = { id: number; type: string; data: { text?: string } };

// A fila de leitura não altera nem bloqueia os eventos recebidos do servidor.
export class Playback<T extends PlayableEvent> {
  source: T[] = [];
  visible: T[] = [];
  cursor = 0;
  characters = 0;
  elapsed = 0;
  waiting = false;
  paused = false;
  automatic = false;
  speed = 1;

  get typing() {
    return this.source[this.cursor]?.type === 'speech' && !this.waiting;
  }
  get pending() {
    return this.cursor < this.source.length;
  }
  sync(events: T[]) {
    this.source = events;
  }
  reset() {
    this.visible = [];
    this.cursor = this.characters = this.elapsed = 0;
    this.waiting = this.paused = false;
  }
  next() {
    this.paused = false;
    const event = this.source[this.cursor];
    if (!event) return;
    if (event.type === 'speech' && !this.waiting) {
      this.show(event);
      this.characters = Array.from(event.data.text || '').length;
      this.waiting = true;
      this.elapsed = 0;
    } else {
      this.show(event);
      this.cursor++;
      this.characters = this.elapsed = 0;
      this.waiting = false;
    }
  }
  showAll() {
    this.visible = [...this.source];
    this.cursor = this.source.length;
    this.waiting = this.paused = false;
    this.characters = this.elapsed = 0;
  }
  private show(event: T) {
    const index = this.visible.findIndex(item => item.id === event.id);
    this.visible = index < 0 ? [...this.visible, event] :
      this.visible.map((item, i) => i === index ? event : item);
  }
  tick(milliseconds: number) {
    if (this.paused || !this.pending) return false;
    const event = this.source[this.cursor];
    this.elapsed += milliseconds * this.speed;
    if (event.type === 'speech') {
      if (this.waiting) {
        if (this.automatic && this.elapsed >= 3500) this.next();
        return false;
      }
      const letters = Array.from(event.data.text || '');
      this.characters += milliseconds * this.speed * 0.035;
      this.show({ ...event, data: { ...event.data, text: letters.slice(0, Math.floor(this.characters)).join('') } });
      if (this.characters >= letters.length) {
        this.show(event);
        this.waiting = true;
        this.elapsed = 0;
      }
      return true;
    }
    if (this.elapsed < (event.type === 'stage' ? 900 : 80)) return false;
    this.show(event);
    this.cursor++;
    this.elapsed = this.characters = 0;
    return true;
  }
}
