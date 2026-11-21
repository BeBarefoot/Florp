import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/", name: "Florp Floor Plans", short_name: "Florp",
    description: "Review floor plans and walk through your space in 3D.",
    start_url: "/", scope: "/", display: "standalone",
    background_color: "#f7f8fa", theme_color: "#121d2e",
    icons: [192, 512].map(size => ({
      src: `/florp-${size}.png`, sizes: `${size}x${size}`, type: "image/png",
    })),
  };
}
