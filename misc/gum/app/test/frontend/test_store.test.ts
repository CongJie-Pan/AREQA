import { describe, it, expect, beforeEach } from 'vitest';
import { useStore } from '../../frontEnd/src/store/useStore';

describe('useStore Zustand store', () => {
  beforeEach(() => {
    // Reset store state
    useStore.setState({
      isRecording: false,
      userName: 'default_user',
      modelName: 'gpt-4o-mini',
      propositions: [],
      suggestions: []
    });
  });

  it('should initialize with default values', () => {
    const state = useStore.getState();
    expect(state.isRecording).toBe(false);
    expect(state.userName).toBe('default_user');
  });

  it('should update recording state', () => {
    useStore.setState({ isRecording: true });
    expect(useStore.getState().isRecording).toBe(true);
  });

  it('should set propositions', () => {
    const mockProps = [
      { id: 1, text: 'test prop', reasoning: 'reason', confidence: 10, created_at: 'now' }
    ];
    useStore.setState({ propositions: mockProps });
    expect(useStore.getState().propositions).toHaveLength(1);
    expect(useStore.getState().propositions[0].text).toBe('test prop');
  });

  it('should fetch memory and update state', async () => {
    const axios = await import('axios');
    // We expect vi.mock('axios') to have been called globally in setup
    // but let's mock it just for this test specifically
    const getMock = vi.mocked(axios.default.get);
    getMock.mockResolvedValueOnce({
      data: {
        propositions: [{ id: 2, text: 'Fetched prop', reasoning: 'Mocked axios', confidence: 5 }]
      }
    });

    await useStore.getState().fetchMemory();

    const state = useStore.getState();
    expect(getMock).toHaveBeenCalledWith('http://localhost:8000/api/memory');
    expect(state.propositions).toHaveLength(1);
    expect(state.propositions[0].text).toBe('Fetched prop');
  });
});
