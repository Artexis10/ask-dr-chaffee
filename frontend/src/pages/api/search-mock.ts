import { NextApiRequest, NextApiResponse } from 'next';

interface SearchResult {
  id: number;
  title: string;
  text: string;
  url: string;
  start_time_seconds: number;
  end_time_seconds: number;
  similarity: string;
  source_type: string;
}

// Mock data for testing the UI
const mockResults: SearchResult[] = [
  {
    id: 1,
    title: "Why the Carnivore Diet Is Helping MILLIONS of People Worldwide!",
    text: "Welcome. I'm John the carnivore teacher and today I am honored to welcome a man who is challenging and changing the way the world thinks about food. Dr. Anthony Chaffy is a medical doctor, neurosurgical registar, former professional rugby player and one of the most outspoken voices in the nutritional space.",
    url: "https://www.youtube.com/watch?v=PL31nbQPgQU&t=1s",
    start_time_seconds: 1.67,
    end_time_seconds: 46.16,
    similarity: "89.5",
    source_type: "youtube"
  },
  {
    id: 2,
    title: "Why the Carnivore Diet Is Helping MILLIONS of People Worldwide!",
    text: "Plants are not the safe, benevolent foods we think they are. In fact, he says they've been trying to kill us all along. Today we're going to dig into exactly what he means by that, how plant toxins work, and why he believes the carnivore diet is the optimal human diet for health, longevity, and disease prevention.",
    url: "https://www.youtube.com/watch?v=PL31nbQPgQU&t=43s",
    start_time_seconds: 43.84,
    end_time_seconds: 87.2,
    similarity: "92.1",
    source_type: "youtube"
  },
  {
    id: 3,
    title: "Why the Carnivore Diet Is Helping MILLIONS of People Worldwide!",
    text: "So in those patients um when they're able to stick to a very strict carnivore diet especially just beef, lamb and water because those ruminant that ruminant digestion can ferment and break down these toxins. Again fermentation that's a good way of getting rid of these plant toxins opening up bioavailability of these nutrients that they are able to break down a lot of these toxins so they don't filter through.",
    url: "https://www.youtube.com/watch?v=PL31nbQPgQU&t=997s",
    start_time_seconds: 997.199,
    end_time_seconds: 1040.319,
    similarity: "88.7",
    source_type: "youtube"
  },
  {
    id: 4,
    title: "Why the Carnivore Diet Is Helping MILLIONS of People Worldwide!",
    text: "Carnivore, which is a ketogenic diet, but it's just a sort of a more another step down that path that they they end up, you know, maybe hit a stall. They massive improvements, health is getting so much better, but they sort of hit a stall. They can't quite get rid of that last little bit of weight and improve their health in certain ways. They get rid of the plants and just that's just the the floodgates open on their health improvements and weight loss.",
    url: "https://www.youtube.com/watch?v=PL31nbQPgQU&t=1245s",
    start_time_seconds: 1245.44,
    end_time_seconds: 1288.24,
    similarity: "91.3",
    source_type: "youtube"
  },
  {
    id: 5,
    title: "Dr. Chaffee Zoom Session - Autoimmune Recovery",
    text: "Many patients I see with autoimmune conditions like rheumatoid arthritis, Hashimoto's thyroiditis, and inflammatory bowel disease show remarkable improvement on a carnivore elimination diet. The removal of plant antigens and inflammatory compounds allows the immune system to reset and heal.",
    url: "https://zoom.us/rec/share/example123?pwd=abc&t=120s",
    start_time_seconds: 120,
    end_time_seconds: 180,
    similarity: "85.4",
    source_type: "zoom"
  }
];

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse
) {
  if (req.method !== 'POST' && req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { query } = req.method === 'POST' ? req.body : req.query;

  if (!query || typeof query !== 'string' || query.trim().length === 0) {
    return res.status(400).json({ error: 'Query is required' });
  }

  try {
    // Filter mock results based on query
    const filteredResults = mockResults.filter(result => 
      result.text.toLowerCase().includes(query.toLowerCase()) ||
      result.title.toLowerCase().includes(query.toLowerCase())
    );

    // Sort by similarity score (descending)
    filteredResults.sort((a, b) => parseFloat(b.similarity) - parseFloat(a.similarity));

    res.status(200).json({ 
      results: filteredResults, 
      total: filteredResults.length, 
      query: query.trim() 
    });
  } catch (err) {
    console.error('Mock search error:', err);
    res.status(500).json({ 
      error: err instanceof Error ? err.message : 'Search failed' 
    });
  }
}
