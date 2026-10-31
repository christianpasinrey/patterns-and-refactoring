using Shop.Services;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddHttpClient<TrackingClient>(client =>
{
    client.BaseAddress = new Uri("https://carrier.example/");
});

var app = builder.Build();

app.MapGet("/track/{number}", (string number, TrackingClient tracking) => tracking.StatusAsync(number));

app.Run();
