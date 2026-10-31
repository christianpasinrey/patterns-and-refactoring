<?php

namespace App\Services;

use Illuminate\Support\Facades\Http;

class TrackingClient
{
    public function status(string $trackingNumber): array
    {
        return Http::get("https://carrier.example/track/{$trackingNumber}")->throw()->json();
    }
}
