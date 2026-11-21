import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // Keep the development indicator from covering app controls during browser tests.
  devIndicators: process.env.FLORP_BROWSER_TEST === '1' ? false : undefined,
};

export default nextConfig;
