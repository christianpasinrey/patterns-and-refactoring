<?php

namespace App\Actions;

use App\Models\Review;

class PublishReview
{
    public function handle(Review $review): Review
    {
        $review->update(['published_at' => now()]);

        return $review;
    }
}
