import React, { useEffect } from 'react';
import { driver } from 'driver.js';
import 'driver.js/dist/driver.css';
import { useStore } from '../store/useStore';

const TourGuide: React.FC = () => {
  const { setCurrentPage } = useStore();

  useEffect(() => {
    // Only run the tour once for new users
    const hasCompletedTour = localStorage.getItem('gumbo_tour_done');
    if (hasCompletedTour) return;

    const tour = driver({
      showProgress: true,
      animate: true,
      allowClose: true,
      doneBtnText: 'Got it!',
      nextBtnText: 'Next',
      prevBtnText: 'Back',
      steps: [
        {
          element: '#tour-step-settings',
          popover: {
            title: 'Welcome to Gumbo! 👋',
            description: 'First, you need to configure your API key. Click here to go to the Settings page and enter your OpenAI API key.',
            side: 'right',
            align: 'start',
            onNextClick: () => {
              setCurrentPage('settings');
              tour.moveNext();
            }
          }
        },
        {
          element: '#tour-step-record',
          popover: {
            title: 'Start the Engine',
            description: 'After saving your API key, click this button to start the background observer. It will simulate observing your actions.',
            side: 'right',
            align: 'end'
          }
        },
        {
          element: '#tour-step-memory',
          popover: {
            title: 'View Memories',
            description: 'Once recording starts, Gumbo will process your actions into structured Propositions here.',
            side: 'right',
            align: 'start',
            onNextClick: () => {
              setCurrentPage('memory');
              tour.moveNext();
            }
          }
        },
        {
          element: '#tour-step-suggestions',
          popover: {
            title: 'Get Actionable Advice',
            description: 'When enough memory is collected, Gumbo provides smart, proactive suggestions for you in this tab!',
            side: 'right',
            align: 'start',
            onNextClick: () => {
              setCurrentPage('suggestions');
              tour.moveNext();
            }
          }
        }
      ],
      onDestroyStarted: () => {
        // Mark tour as done whether they finished or closed it early
        localStorage.setItem('gumbo_tour_done', 'true');
        tour.destroy();
      }
    });

    // Small delay to ensure DOM is ready
    const timer = setTimeout(() => {
      tour.drive();
    }, 500);

    return () => clearTimeout(timer);
  }, [setCurrentPage]);

  return null; // This is an invisible utility component
};

export default TourGuide;
