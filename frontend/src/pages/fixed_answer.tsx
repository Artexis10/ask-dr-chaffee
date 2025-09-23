// Function to call answer API - FIXED VERSION
const performAnswer = useCallback(async (searchQuery: string) => {
  if (!searchQuery.trim()) return;
  
  setAnswerLoading(true);
  setAnswerError('');
  setAnswerData(null);
  
  try {
    const params = new URLSearchParams({
      q: searchQuery,
      style: 'concise'
    });
    
    console.log('Answer API call URL:', `/api/answer?${params}`);
    
    const response = await fetch(`/api/answer?${params}`);
    let responseData;
    
    try {
      // Read the response body only once
      responseData = await response.json();
    } catch (jsonError) {
      console.error('Failed to parse response as JSON:', jsonError);
      throw new Error(`Failed to parse response: ${jsonError.message}`);
    }
    
    if (!response.ok) {
      throw new Error(responseData?.error || `Answer failed with status: ${response.status}`);
    }
    
    console.log('Answer API response:', responseData);
    
    if (responseData.error) {
      // Handle cases like "Not enough on-record context yet"
      setAnswerError(responseData.error);
    } else {
      setAnswerData(responseData);
    }
    
  } catch (err) {
    console.error('Answer error:', err);
    const errorMessage = err instanceof Error ? err.message : 
                        typeof err === 'string' ? err : 
                        'Failed to generate answer';
    setAnswerError(errorMessage);
  } finally {
    setAnswerLoading(false);
  }
}, []);
