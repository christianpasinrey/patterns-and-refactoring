<?php

namespace App\Http\Controllers;

use App\Actions\PublishReview;
use App\Models\Review;

class ReviewController
{
    public function publish(Review $review, PublishReview $action)
    {
        return $action->handle($review);
    }
}
