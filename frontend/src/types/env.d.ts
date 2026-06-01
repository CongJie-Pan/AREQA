/**
 * Environment variable type definitions
 * Ensures type safety when accessing environment variables
 */

declare namespace NodeJS {
  interface ProcessEnv {
    /** Perplexity API Key - Required for API calls */
    PERPLEXITY_API_KEY: string;

    /** Node environment */
    NODE_ENV: 'development' | 'production' | 'test';
  }
}
