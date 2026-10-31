<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class OauthToken extends Model
{
    protected $fillable = ['mailbox_id', 'access_token', 'expires_at'];
}
