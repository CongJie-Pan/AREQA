import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import Sidebar from '../../frontEnd/src/components/Sidebar';
import { useStore } from '../../frontEnd/src/store/useStore';
import axios from 'axios';

vi.mock('axios');



describe('Sidebar Component', () => {
  beforeEach(() => {
    // @ts-ignore
    axios.get.mockResolvedValue({ data: { is_recording: false } });
    // @ts-ignore
    axios.post.mockResolvedValue({ data: {} });
  });

  it('renders application title', () => {
    render(<Sidebar />);
    expect(screen.getByText('Gumbo')).toBeInTheDocument();
  });

  it('calls setCurrentPage when navigation buttons are clicked', () => {
    const setCurrentPageMock = vi.fn();
    useStore.setState({ setCurrentPage: setCurrentPageMock });
    render(<Sidebar />);
    
    // Click memory tab
    fireEvent.click(screen.getByText('Memory'));
    expect(setCurrentPageMock).toHaveBeenCalledWith('memory');
  });
  
  it('renders start recording when not recording', () => {
    useStore.setState({ isRecording: false });
    render(<Sidebar />);
    
    expect(screen.getByText('Start Recording')).toBeInTheDocument();
  });

  it('renders stop recording when recording', () => {
    useStore.setState({ isRecording: true });
    render(<Sidebar />);
    
    expect(screen.getByText('Stop Recording')).toBeInTheDocument();
  });
});
