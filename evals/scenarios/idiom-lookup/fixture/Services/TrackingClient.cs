using System.Text.Json;

namespace Shop.Services;

public class TrackingClient(HttpClient http)
{
    public async Task<JsonElement> StatusAsync(string trackingNumber)
    {
        var response = await http.GetAsync($"track/{trackingNumber}");
        response.EnsureSuccessStatusCode();

        return await response.Content.ReadFromJsonAsync<JsonElement>();
    }
}
