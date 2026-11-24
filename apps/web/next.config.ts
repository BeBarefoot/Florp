import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // Keep development tools clear of the phone tour's bottom-left dock.
  devIndicators: process.env.FLORP_BROWSER_TEST === '1' ? false : { position: 'top-right' },
};

export default nextConfig;
