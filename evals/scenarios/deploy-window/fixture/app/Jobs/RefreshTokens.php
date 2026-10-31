<?php

namespace App\Jobs;

use App\Models\OauthToken;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Support\Facades\Http;

/** Runs every minute on Horizon, 24/7. Three failures disable the mailbox. */
class RefreshTokens implements ShouldQueue
{
    public function handle(): void
    {
        OauthToken::where('expires_at', '<', now()->addMinutes(5))->each(function (OauthToken $token) {
            $response = Http::withToken($token->access_token)->post('https://login.example/refresh');
            if ($response->failed()) {
                $token->increment('failures');
            }
        });
    }
}
