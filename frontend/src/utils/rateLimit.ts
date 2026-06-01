/**
 * Rate Limiting Utility
 * Simple in-memory rate limiter for API endpoints
 * Uses sliding window algorithm
 */

interface RateLimitEntry {
  count: number;
  resetTime: number;
}

/** Rate limit configuration */
interface RateLimitConfig {
  /** Maximum requests allowed */
  maxRequests: number;
  /** Time window in milliseconds */
  windowMs: number;
}

/** Default rate limit: 20 requests per minute */
const DEFAULT_CONFIG: RateLimitConfig = {
  maxRequests: 20,
  windowMs: 60_000,
};

/** In-memory store for rate limit entries */
const rateLimitStore = new Map<string, RateLimitEntry>();

/** Cleanup interval (5 minutes) */
const CLEANUP_INTERVAL = 5 * 60 * 1000;

/**
 * Periodically clean up expired entries to prevent memory leaks
 */
let cleanupTimer: NodeJS.Timeout | null = null;

function startCleanup(): void {
  if (cleanupTimer) return;

  cleanupTimer = setInterval(() => {
    const now = Date.now();
    for (const [key, entry] of rateLimitStore.entries()) {
      if (entry.resetTime < now) {
        rateLimitStore.delete(key);
      }
    }
  }, CLEANUP_INTERVAL);

  // Allow process to exit if this is the only timer
  if (cleanupTimer.unref) {
    cleanupTimer.unref();
  }
}

/**
 * Extracts client identifier from request
 * Uses X-Forwarded-For header or falls back to a default
 * @param request - The incoming request
 * @returns Client identifier string
 */
export function getClientIdentifier(request: Request): string {
  const forwardedFor = request.headers.get('x-forwarded-for');
  if (forwardedFor) {
    // Get first IP in chain (original client)
    return forwardedFor.split(',')[0].trim();
  }

  const realIp = request.headers.get('x-real-ip');
  if (realIp) {
    return realIp;
  }

  // Fallback for development/testing
  return 'unknown-client';
}

/**
 * Rate limit result
 */
export interface RateLimitResult {
  /** Whether the request is allowed */
  allowed: boolean;
  /** Remaining requests in current window */
  remaining: number;
  /** Time until rate limit resets (seconds) */
  resetIn: number;
  /** Total requests allowed */
  limit: number;
}

/**
 * Checks if a request should be rate limited
 * @param identifier - Client identifier (IP or user ID)
 * @param config - Rate limit configuration
 * @returns Rate limit result
 */
export function checkRateLimit(
  identifier: string,
  config: RateLimitConfig = DEFAULT_CONFIG
): RateLimitResult {
  startCleanup();

  const now = Date.now();
  const entry = rateLimitStore.get(identifier);

  // If no entry or expired, create new window
  if (!entry || entry.resetTime < now) {
    const newEntry: RateLimitEntry = {
      count: 1,
      resetTime: now + config.windowMs,
    };
    rateLimitStore.set(identifier, newEntry);

    return {
      allowed: true,
      remaining: config.maxRequests - 1,
      resetIn: Math.ceil(config.windowMs / 1000),
      limit: config.maxRequests,
    };
  }

  // Increment count
  entry.count += 1;

  const resetIn = Math.ceil((entry.resetTime - now) / 1000);
  const remaining = Math.max(0, config.maxRequests - entry.count);
  const allowed = entry.count <= config.maxRequests;

  return {
    allowed,
    remaining,
    resetIn,
    limit: config.maxRequests,
  };
}

/**
 * Resets rate limit for a specific identifier
 * Useful for testing
 * @param identifier - Client identifier to reset
 */
export function resetRateLimit(identifier: string): void {
  rateLimitStore.delete(identifier);
}

/**
 * Clears all rate limit entries
 * Useful for testing
 */
export function clearAllRateLimits(): void {
  rateLimitStore.clear();
}
